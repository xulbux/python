#!/usr/bin/env python3
# x-cmds:file[update]

"""
Clean broken registry entries, environment variables, shortcuts and temp files.
"""

import contextlib
import json
import os
import subprocess
import winreg
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
import xulbux as xx
from xulbux import ArgumentParser, S, Throbber

if TYPE_CHECKING:
    from ._shared.helpers import format_size

    from xulbux.ansi import TextRenderable

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared.helpers import format_size

try:
    from win32com.client import Dispatch as COMDispatch

    HAS_WIN32COM = True

except ImportError:
    COMDispatch = None
    HAS_WIN32COM = False  # pyright:ignore[reportConstantRedefinition]

# ********************************************************* CONSTANTS *********************************************************

BACKUPS_DIR = xx.fs.get_script_dir() / "backups"

# Registry paths to scan for broken entries:
REGISTRY_APP_PATHS: list[tuple[int, str]] = [
    (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\App Paths"),
    (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths"),
]
REGISTRY_UNINS_PATHS: list[tuple[int, str]] = [
    (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"),
]
REGISTRY_STARTUP_PATHS: list[tuple[int, str]] = [
    (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Run"),
    (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"),
    (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Run"),
    (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\RunOnce"),
]

# Values in uninstall keys that indicate whether the software is actually installed.
# Note: `InstallSource` & `DisplayIcon` excluded because they're informational and don't indicate the software is uninstalled:
PATH_VALUE_NAMES = {"UninstallString", "QuietUninstallString", "InstallLocation", "ModifyPath"}

# Environment variable registry locations:
ENV_USER_KEY: tuple[int, str] = (winreg.HKEY_CURRENT_USER, "Environment")
ENV_SYSTEM_KEY: tuple[int, str] = (
    winreg.HKEY_LOCAL_MACHINE,
    "SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",
)

# Shortcut directories to scan:
SHORTCUT_DIRS: list[tuple[str, Path]] = []


def _build_shortcut_dirs() -> list[tuple[str, Path]]:
    """Build list of shortcut directories to scan."""

    dirs: list[tuple[str, Path]] = []
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", "")
    userprofile = os.environ.get("USERPROFILE", "")
    public = os.environ.get("PUBLIC", "")

    if appdata:
        dirs.append(("User Startup", Path(appdata) / "Microsoft\\Windows\\Start Menu\\Programs\\Startup"))
        dirs.append(("User Start Menu", Path(appdata) / "Microsoft\\Windows\\Start Menu\\Programs"))
    if programdata:
        dirs.append(("Global Startup", Path(programdata) / "Microsoft\\Windows\\Start Menu\\Programs\\Startup"))
        dirs.append(("Global Start Menu", Path(programdata) / "Microsoft\\Windows\\Start Menu\\Programs"))
    if userprofile:
        dirs.append(("User Desktop", Path(userprofile) / "Desktop"))
    if public:
        dirs.append(("Public Desktop", Path(public) / "Desktop"))

    return dirs


HIVE_NAMES = {winreg.HKEY_CURRENT_USER: "HKCU", winreg.HKEY_LOCAL_MACHINE: "HKLM"}


# ********************************************************** HELPERS **********************************************************


def hive_name(hive: int) -> str:
    """Get readable name for a registry hive."""

    return HIVE_NAMES.get(hive, str(hive))


def extract_path_from_value(value: str) -> Path | None:
    """Extract a file/directory path from a registry value string.<br>
    Handles quoted paths, paths with args, MsiExec, rundll32, etc."""

    if not value:
        return None
    if not (stripped := value.strip()):
        return None

    # Skip commands without directory slashes (e.g., `cmd.exe /c …`, `rundll32.exe`, `msiexec`):
    if "\\" not in stripped and "/" not in stripped:
        return None

    # Skip msiexec and rundll32 entries; they don't point to real uninstallers on disk:
    if (lower := stripped.lower()).startswith("msiexec") or lower.startswith("rundll32"):
        return None

    # Handle quoted paths (`"C:\path\to\file.exe" /args`); only accept absolute paths or env var paths:
    if stripped.startswith('"') and (end := stripped.find('"', 1)) != -1 and looks_like_path(candidate := stripped[1:end]):
        return Path(candidate)

    # Handle paths with arguments: `C:\path\file.exe /arg`.
    # Look for .exe or other executable extensions:
    for ext in (".exe", ".msi", ".bat", ".cmd", ".com"):
        if (idx := lower.find(ext)) != -1 and looks_like_path(candidate := stripped[: idx + len(ext)]):
            return Path(candidate)

    # Handle display icon format `path.exe,0`:
    if "," in stripped and (candidate := stripped.split(",")[0].strip().strip('"')) and looks_like_path(candidate):
        return Path(candidate)

    # Final fallback:
    if looks_like_path(stripped):
        return Path(stripped)

    return None


def refresh_env_from_registry() -> None:
    """Refresh `os.environ` with live environment variables from the Windows registry.<br>
    Loads System variables first, then User variables (allowing user variables to override)."""

    # [1] Read variables from System registry, then User registry:
    for hive, reg_path in (ENV_SYSTEM_KEY, ENV_USER_KEY):
        try:
            key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_READ)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    name, val_data, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1

                # Skip `PATH` (to avoid overriding process-level combined `PATH`):
                if name.upper() == "PATH":
                    continue

                os.environ[name] = str(val_data)

        finally:
            winreg.CloseKey(key)

    # [2] Multi-pass expand environment variables containing nested references:
    for _ in range(3):
        has_changed = False

        for env_name, env_value in list(os.environ.items()):
            if "%" in env_value and (expanded_val := str(os.path.expandvars(env_value))) != env_value:
                os.environ[env_name] = expanded_val
                has_changed = True

        if not has_changed:
            break


def expand_env_in_path(value: str) -> str:
    """Expand environment variable references like `%USERPROFILE%` in a string."""

    expanded = str(os.path.expandvars(value))
    for _ in range(3):
        if "%" not in expanded:
            break
        if (next_expanded := str(os.path.expandvars(expanded))) == expanded:
            break
        expanded = next_expanded

    return expanded


def path_exists(path: Path) -> bool:
    """Check if a path exists, handling long paths and permission issues.<br>
    Also expands environment variable references like `%USERPROFILE%`."""

    try:
        return Path(expand_env_in_path(str(path))).exists()
    except (OSError, PermissionError, ValueError):
        return False


def looks_like_path(value: str) -> bool:
    """Check if a string value looks like it could be a filesystem path."""

    if not value:
        return False
    if not (stripped := value.strip().strip('"')):
        return False

    # Expand environment variables first:
    expanded = expand_env_in_path(stripped)

    # Absolute paths (`C:\…`, `\\server\…`):
    if len(expanded) >= 3 and expanded[1:3] == ":\\":
        return True
    if expanded.startswith("\\\\"):
        return True

    # Environment variable references that look like paths (e.g., `%SYSTEMROOT%\…`):
    if "%" in stripped and ("\\" in stripped or "/" in stripped):
        return True

    # Paths with path separators and typical extensions/directories:
    if "\\" in stripped or "/" in stripped:
        lowered = stripped.lower()
        for segment in {"program files", "windows", "users", "appdata"}:
            if segment in lowered:
                return True

    return False


def resolve_shortcut(lnk_path: Path) -> Path | None:
    """Resolve a `.lnk` shortcut file to its target path."""

    if not HAS_WIN32COM or COMDispatch is None:
        return None

    try:
        if target := COMDispatch("WScript.Shell").CreateShortcut(str(lnk_path)).TargetPath:
            return Path(target)
        return None

    except Exception:
        return None


# ********************************************************* SCANNING **********************************************************


def scan_registry_app_paths() -> list[dict[str, Any]]:
    """Scan App Paths registry keys for entries with broken paths.\n
    -----------------------------------------------------------------
    Returns list of dicts: `{hive, path, subkey, broken_path}`"""

    issues: list[dict[str, Any]] = []

    for hive, reg_path in REGISTRY_APP_PATHS:
        try:
            root_key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(root_key, i)
                except OSError:
                    break
                i += 1

                full_path = f"{reg_path}\\{subkey_name}"
                try:
                    subkey = winreg.OpenKey(hive, full_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                except OSError:
                    continue

                # Check default value (the app path):
                with suppress(OSError):
                    val_data, val_type = winreg.QueryValueEx(subkey, "")
                    if val_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and val_data:
                        path = extract_path_from_value(str(val_data))
                        if path is not None and not path_exists(path):
                            issues.append({
                                "hive": hive,
                                "path": full_path,
                                "subkey": subkey_name,
                                "broken_path": str(val_data),
                            })

                winreg.CloseKey(subkey)
        finally:
            winreg.CloseKey(root_key)

    return issues


def scan_registry_unins_paths() -> list[dict[str, Any]]:
    """Scan uninstall registry keys for entries with broken paths.\n
    ------------------------------------------------------------------------------
    Returns list of dicts: `{hive, path, subkey, display_name, broken_values}`"""

    issues: list[dict[str, Any]] = []

    for hive, reg_path in REGISTRY_UNINS_PATHS:
        try:
            root_key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(root_key, i)
                except OSError:
                    break
                i += 1

                full_path = f"{reg_path}\\{subkey_name}"
                try:
                    subkey = winreg.OpenKey(hive, full_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                except OSError:
                    continue

                # Get display name:
                display_name = subkey_name
                with contextlib.suppress(OSError):
                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]

                # Check all path values in this key:
                broken_values: list[tuple[str, str]] = []
                has_any_valid = False

                for val_name in PATH_VALUE_NAMES:
                    try:
                        val_data, val_type = winreg.QueryValueEx(subkey, val_name)
                    except OSError:
                        continue

                    if val_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                        continue

                    p = extract_path_from_value(str(val_data))
                    if p is None:
                        continue

                    if path_exists(p):
                        has_any_valid = True
                    else:
                        broken_values.append((val_name, str(val_data)))

                winreg.CloseKey(subkey)

                # If we found broken paths and no valid paths, flag the entire entry:
                if broken_values and not has_any_valid:
                    issues.append({
                        "hive": hive,
                        "path": full_path,
                        "subkey": subkey_name,
                        "display_name": display_name,
                        "broken_values": broken_values,
                    })
        finally:
            winreg.CloseKey(root_key)

    return issues


def scan_registry_startup_paths() -> list[dict[str, Any]]:
    """Scan `Run`/`RunOnce` registry keys for values pointing to non-existent paths.\n
    -----------------------------------------------------------------------------------
    Returns list of dicts: `{hive, path, value_name, value_data, value_type}`"""

    issues: list[dict[str, Any]] = []

    for hive, reg_path in REGISTRY_STARTUP_PATHS:
        try:
            key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    name, value, val_type = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1

                if val_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                    continue

                p = extract_path_from_value(str(value))
                if p is None:
                    continue

                if not path_exists(p):
                    issues.append({
                        "hive": hive,
                        "path": reg_path,
                        "value_name": name,
                        "value_data": str(value),
                        "value_type": val_type,
                    })
        finally:
            winreg.CloseKey(key)

    return issues


def scan_env_vars() -> dict[str, list[dict[str, Any]]]:
    """Scan environment variables for broken paths.\n
    ----------------------------------------------------------------------------------
    Returns dict with keys `user` and `system`, each containing a list of issues:<br>
    `{name, value_type, original_value, broken_paths, scope}`"""

    refresh_env_from_registry()
    return {
        scope: _scan_env_scope(scope, hive, reg_path)
        for scope, (hive, reg_path) in (("user", ENV_USER_KEY), ("system", ENV_SYSTEM_KEY))
    }


def _scan_env_scope(scope: str, hive: int, reg_path: str) -> list[dict[str, Any]]:
    """Scan a single environment scope (user or system) for broken paths."""

    try:
        key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_READ)
    except OSError:
        return []

    issues: list[dict[str, Any]] = []

    try:
        i = 0
        while True:
            try:
                name, value, val_type = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1

            if val_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                continue

            str_value = str(value)
            is_path_list = False
            if ";" in str_value:
                for item in str_value.split(";"):
                    if looks_like_path(item):
                        is_path_list = True
                        break

            if is_path_list:
                paths = [path_entry.strip() for path_entry in str_value.split(";") if path_entry.strip()]
                broken = [
                    path_entry
                    for path_entry in paths
                    if looks_like_path(path_entry) and not path_exists(Path(expand_env_in_path(path_entry.strip('"'))))
                ]
                if broken:
                    issues.append({
                        "name": name,
                        "value_type": val_type,
                        "original_value": str_value,
                        "broken_paths": broken,
                        "scope": scope,
                    })

            elif looks_like_path(str_value):
                candidate_path = Path(expand_env_in_path(str_value.strip().strip('"')))
                if not path_exists(candidate_path):
                    issues.append({
                        "name": name,
                        "value_type": val_type,
                        "original_value": str_value,
                        "broken_paths": [str_value],
                        "scope": scope,
                    })

    finally:
        winreg.CloseKey(key)

    return issues


def scan_shortcuts() -> list[dict[str, Any]]:
    """Scan shortcut directories for broken `.lnk` files.\n
    -----------------------------------------------------------------
    Returns list of dicts: `{label, dir_path, broken_shortcuts}`<br>
    where broken_shortcuts is list of `{lnk_path, target}`"""

    if not HAS_WIN32COM:
        return []

    issues: list[dict[str, Any]] = []
    shortcut_dirs = _build_shortcut_dirs()

    for label, dir_path in shortcut_dirs:
        if not dir_path.exists():
            continue

        broken_shortcuts: list[dict[str, Any]] = []
        _scan_shortcuts_recursive(dir_path, broken_shortcuts)

        if broken_shortcuts:
            issues.append({"label": label, "dir_path": dir_path, "broken_shortcuts": broken_shortcuts})

    return issues


def _scan_shortcuts_recursive(directory: Path, broken_list: list[dict[str, Any]]) -> None:
    """Recursively scan a directory for broken shortcuts."""

    try:
        entries = list(directory.iterdir())
    except (PermissionError, OSError):
        return

    for entry in entries:
        if entry.is_dir():
            _scan_shortcuts_recursive(entry, broken_list)
        elif entry.suffix.lower() == ".lnk" and (target := resolve_shortcut(entry)) is not None and not path_exists(target):
            broken_list.append({"lnk_path": entry, "target": str(target)})


def scan_temp_files() -> dict[str, list[dict[str, Any]]]:
    """Scan temp directories for cleanable files.\n
    -----------------------------------------------------------
    Returns dict with key `dirs` containing list of dicts:<br>
    `{dirs: [{path, file_count, size_bytes}]}`"""

    temp_dirs_to_check: list[tuple[str, Path]] = []

    # Windows temp:
    win_temp = Path(os.environ.get("TEMP", ""))
    if win_temp.exists():
        temp_dirs_to_check.append(("User Temp", win_temp))

    # System temp:
    sys_temp = Path("C:\\Windows\\Temp")
    if sys_temp.exists():
        temp_dirs_to_check.append(("System Temp", sys_temp))

    # Prefetch:
    prefetch = Path("C:\\Windows\\Prefetch")
    if prefetch.exists():
        temp_dirs_to_check.append(("Prefetch", prefetch))

    result: list[dict[str, Any]] = []
    for label, dir_path in temp_dirs_to_check:
        file_count = 0
        total_size = 0
        with suppress(PermissionError, OSError):
            for f in dir_path.rglob("*"):
                if f.is_file():
                    file_count += 1
                    with contextlib.suppress(OSError, PermissionError):
                        total_size += f.stat().st_size

        if file_count > 0:
            result.append({"label": label, "path": dir_path, "file_count": file_count, "size_bytes": total_size})

    return {"dirs": result}


# ********************************************************** BACKUPS **********************************************************


def create_backup_dir() -> Path:
    """Create a timestamped backup directory."""

    backup_dir = BACKUPS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_registry(backup_dir: Path) -> bool:
    """Export uninstall and app paths registry keys to `.reg` files."""

    all_locations = REGISTRY_APP_PATHS + REGISTRY_UNINS_PATHS + REGISTRY_STARTUP_PATHS
    success = True

    for hive, reg_path in all_locations:
        full_path = f"{hive_name(hive)}\\{reg_path}"
        safe_name = reg_path.replace("\\", "_")
        filename = f"{hive_name(hive)}_{safe_name}.reg"
        export_path = backup_dir / filename

        # Skip non-existent keys (`RunOnce` often missing):
        try:
            test_key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            winreg.CloseKey(test_key)
        except OSError:
            S.DIM(f"  · Skipped missing key ({full_path})").print()
            continue

        try:
            result = subprocess.run(
                ["reg", "export", full_path, str(export_path), "/y"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if result.returncode != 0:
                S(S.YELLOW("  ⚠ Failed to export ", S.DIM(f"({full_path})"), ":\n"), f"    {result.stderr.strip()}").print()
                success = False
            else:
                S("  ", S.GREEN("✓"), " Exported ", S.DIM(f"({full_path})")).print()

        except Exception as exc:
            S(S.RED("  ✗ Error exporting ", S.DIM(f"({full_path})"), ":\n"), f"    {exc}").print()
            success = False

    return success


def backup_env_vars(backup_dir: Path) -> bool:
    """Backup all environment variables (user + system) to a JSON file."""

    data: dict[str, dict[str, dict[str, Any]]] = {"user": {}, "system": {}}

    for scope, (hive, reg_path) in [("user", ENV_USER_KEY), ("system", ENV_SYSTEM_KEY)]:
        try:
            key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_READ)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    name, value, val_type = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                data[scope][name] = {"value": value, "type": val_type}
        finally:
            winreg.CloseKey(key)

    backup_file = backup_dir / "env_vars_backup.json"
    try:
        backup_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        backup_link = (S.DIM | S.link(backup_file))(backup_file.name)
        S("  ", S.GREEN("✓"), " Saved env vars ", backup_link).print()
        return True
    except Exception as exc:
        S(S.RED("  ✗ Failed to save env vars backup:\n"), f"    {exc}").print()
        return False


# ********************************************************** RESTORE **********************************************************


def restore_env_vars(backup_path: Path) -> None:
    """Restore environment variables from a JSON backup file."""

    if not backup_path.exists():
        xx.console.fail(S("Backup file does not exist: ", S.BR.CYAN(str(backup_path))), start="\n", end="\n\n", exit_code=1)

    backup_link = (S.BR.CYAN | S.link(backup_path))(backup_path.name)
    S.BOLD("\nLoading backup from ", backup_link, "…").print()

    try:
        data = json.loads(backup_path.read_text(encoding="utf-8"))
    except Exception as exc:
        xx.console.fail(f"Failed to read backup file: {exc}", start="\n", end="\n\n", exit_code=1)

    # Show what will be restored:
    for scope in ("user", "system"):
        if data.get(scope):
            S("\n  ", S.BOLD(f"{scope.upper()} variables: "), S.DIM(f"({len(data[scope])} entries)")).print()

    if not xx.console.confirm(S("\n", S.BOLD("Restore these environment variables?")), default_is_yes=False):
        xx.console.exit("Restore canceled.", start="\n", end="\n\n")

    failures: list[str] = []
    restored = 0

    for scope, (hive, reg_path) in [("user", ENV_USER_KEY), ("system", ENV_SYSTEM_KEY)]:
        if scope not in data:
            continue

        for name, var_info in data[scope].items():
            try:
                key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, name, 0, var_info["type"], var_info["value"])
                winreg.CloseKey(key)
                S("  ", S.GREEN("✓"), " Restored ", S.BOLD(scope), S.GREEN("/"), " ", S.CYAN(name)).print()
                restored += 1
            except Exception as exc:
                msg = f"Failed to restore {scope}/{name}: {exc}"
                failures.append(msg)
                S("  ", S.RED("✗"), f" {msg}").print()

    (S.BOLD | S.GREEN)(f"\n✓ Restored {restored} variable(s).").print()
    if failures:
        (S.BOLD | S.RED)(f"✗ {len(failures)} failure(s).\n").print()

    # Broadcast environment change:
    _broadcast_env_change()


def _broadcast_env_change() -> None:
    """Broadcast `WM_SETTINGCHANGE` so other processes pick up env var changes."""

    with suppress(Exception):
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None
        )


# ***************************************************** CLEANUP EXECUTION *****************************************************


def execute_registry_cleanup(
    app_path_issues: list[dict[str, Any]],
    unins_issues: list[dict[str, Any]],
    startup_issues: list[dict[str, Any]],
) -> list[str]:
    """Delete broken registry entries. Returns list of failure messages."""

    failures: list[str] = []

    if app_path_issues:
        S.BOLD("\nCleaning registry App Paths entries...").print()

        for issue in app_path_issues:
            hive = issue["hive"]
            reg_path = issue["path"]
            subkey = issue["subkey"]

            try:
                _delete_registry_tree(hive, reg_path)
                S(
                    "  ",
                    S.GREEN("✓"),
                    " Deleted ",
                    S.MAGENTA(subkey),
                    " ",
                    (S.DIM | S.BR.MAGENTA)(f"{hive_name(hive)}\\{reg_path}"),
                ).print()

            except Exception as exc:
                msg = f"Failed to delete {hive_name(hive)}\\{reg_path}: {exc}"
                failures.append(msg)
                S("  ", S.RED("✗"), f" {msg}").print()

    if unins_issues:
        S.BOLD("\nCleaning registry uninstall entries...").print()

        for issue in unins_issues:
            hive = issue["hive"]
            reg_path = issue["path"]
            display = issue["display_name"]

            try:
                _delete_registry_tree(hive, reg_path)
                S(
                    "  ",
                    S.GREEN("✓"),
                    " Deleted ",
                    S.MAGENTA(display),
                    " ",
                    (S.DIM | S.BR.MAGENTA)(f"{hive_name(hive)}\\{reg_path}"),
                ).print()

            except Exception as exc:
                msg = f"Failed to delete {hive_name(hive)}\\{reg_path}: {exc}"
                failures.append(msg)
                S("  ", S.RED("✗"), f" {msg}").print()

    if startup_issues:
        S.BOLD("\nCleaning registry Run/RunOnce entries...").print()

        for issue in startup_issues:
            hive = issue["hive"]
            reg_path = issue["path"]
            value_name = issue["value_name"]

            try:
                key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
                winreg.DeleteValue(key, value_name)
                winreg.CloseKey(key)
                S(
                    "  ",
                    S.GREEN("✓"),
                    " Deleted ",
                    S.MAGENTA(value_name),
                    " ",
                    (S.DIM | S.BR.MAGENTA)(f"{hive_name(hive)}\\{reg_path}"),
                ).print()

            except Exception as exc:
                msg = f"Failed to delete {hive_name(hive)}\\{reg_path}\\{value_name}: {exc}"
                failures.append(msg)
                S("  ", S.RED("✗"), f" {msg}").print()

    return failures


def _delete_registry_tree(hive: int, key_path: str) -> None:
    """Recursively delete a registry key and all its subkeys."""

    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        return

    # First delete all subkeys recursively:
    try:
        while True:
            try:
                subkey_name = winreg.EnumKey(key, 0)
                _delete_registry_tree(hive, f"{key_path}\\{subkey_name}")
            except OSError:
                break
    finally:
        winreg.CloseKey(key)

    # Now delete the key itself:
    parent_path = "\\".join(key_path.split("\\")[:-1])
    key_name = key_path.split("\\")[-1]

    try:
        parent = winreg.OpenKey(hive, parent_path, 0, winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY)
        winreg.DeleteKey(parent, key_name)
        winreg.CloseKey(parent)
    except OSError as exc:
        raise OSError(f"Could not delete key {key_path}: {exc}") from exc


def execute_env_cleanup(env_issues: dict[str, Any]) -> list[str]:
    """Remove broken paths from environment variables. Returns failure messages."""

    failures: list[str] = []

    for scope, (hive, reg_path) in [("user", ENV_USER_KEY), ("system", ENV_SYSTEM_KEY)]:
        issues = env_issues.get(scope, [])
        if not issues:
            continue

        S.BOLD(f"\nCleaning {scope} environment variables...").print()

        for issue in issues:
            name = issue["name"]
            original = issue["original_value"]
            broken = set(issue["broken_paths"])
            val_type = issue["value_type"]

            try:
                # If the variable contains semicolons, it's a path list; remove only broken parts:
                if ";" in original:
                    paths = [path_entry.strip() for path_entry in original.split(";")]
                    cleaned = [path_entry for path_entry in paths if path_entry and path_entry not in broken]
                    new_value = ";".join(cleaned)

                    if not new_value:
                        # All paths were broken; delete the entire variable:
                        key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_SET_VALUE)
                        winreg.DeleteValue(key, name)
                        winreg.CloseKey(key)
                        S(
                            "  ",
                            S.GREEN("✓"),
                            " Deleted empty variable ",
                            S.CYAN(name),
                            " ",
                            (S.DIM | S.BR.CYAN)(f"from {scope}"),
                        ).print()
                    else:
                        key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_SET_VALUE)
                        winreg.SetValueEx(key, name, 0, val_type, new_value)
                        winreg.CloseKey(key)
                        removed_count = len(broken)
                        count_suffix = "" if removed_count == 1 else "s"
                        S(
                            "  ",
                            S.GREEN("✓"),
                            " Removed ",
                            S.BOLD(str(removed_count)),
                            f" broken path{count_suffix} from ",
                            S.CYAN(name),
                            " ",
                            (S.DIM | S.BR.CYAN)(f"in {scope}"),
                        ).print()

                else:
                    # Entire value is a broken path; delete the variable:
                    key = winreg.OpenKey(hive, reg_path, 0, winreg.KEY_SET_VALUE)
                    winreg.DeleteValue(key, name)
                    winreg.CloseKey(key)
                    S(
                        "  ", S.GREEN("✓"), " Deleted variable ", S.CYAN(name), " ", (S.DIM | S.BR.CYAN)(f"from {scope}")
                    ).print()

            except Exception as exc:
                msg = f"Failed to clean {scope}/{name}: {exc}"
                failures.append(msg)
                S("  ", S.RED("✗"), f" {msg}").print()

    # Broadcast environment change:
    _broadcast_env_change()

    return failures


def execute_shortcut_cleanup(shortcut_issues: list[dict[str, Any]]) -> list[str]:
    """Delete broken shortcuts and empty directories. Returns failure messages."""

    failures: list[str] = []

    S.BOLD("\nCleaning broken shortcuts...").print()

    for location in shortcut_issues:
        label = location["label"]
        S("\n  ", S.BOLD(f"{label}:")).print()

        for shortcut_info in location["broken_shortcuts"]:
            lnk_path: Path = shortcut_info["lnk_path"]
            target = shortcut_info["target"]

            try:
                lnk_path.unlink()
                S("    ", S.GREEN("✓"), " Deleted ", S.BLUE(lnk_path.name), " ", (S.DIM | S.BR.BLUE)(target)).print()
            except Exception as exc:
                msg = f"Failed to delete {lnk_path}: {exc}"
                failures.append(msg)
                S("    ", S.RED("✗"), f" {msg}").print()

    # Clean up empty directories left behind:
    for _, dir_path in _build_shortcut_dirs():
        if dir_path.exists():
            _remove_empty_dirs(dir_path, failures)

    return failures


def _remove_empty_dirs(directory: Path, failures: list[str]) -> bool:
    """Recursively remove empty directories. Returns True if directory was removed."""

    if not directory.is_dir():
        return False

    try:
        entries = list(directory.iterdir())
    except (PermissionError, OSError):
        return False

    # First recurse into subdirectories:
    all_removed = True
    for entry in entries:
        if entry.is_dir():
            if not _remove_empty_dirs(entry, failures):
                all_removed = False
        else:
            all_removed = False

    # Don't remove root shortcut dirs, only their subdirectories:
    shortcut_dirs = _build_shortcut_dirs()
    root_dirs = {shortcut_dir.resolve() for _, shortcut_dir in shortcut_dirs}
    if directory.resolve() in root_dirs:
        return False

    if all_removed:
        try:
            directory.rmdir()
            S("    ", S.GREEN("✓"), " Removed empty directory ", (S.DIM | S.BR.BLUE)(str(directory))).print()
            return True
        except Exception as exc:
            failures.append(f"Failed to remove empty dir {directory}: {exc}")
            return False

    return False


def execute_temp_cleanup(temp_info: dict[str, Any]) -> list[str]:
    """Clean temp directories. Returns failure messages."""

    failures: list[str] = []

    S.BOLD("\nCleaning temp files...").print()

    for dir_info in temp_info["dirs"]:
        label = dir_info["label"]
        dir_path: Path = dir_info["path"]
        dir_display = f"{dir_path.parent.name}/{dir_path.name}"
        S("\n  ", S.BOLD(f"{label}: "), (S.DIM | S.link(dir_path))(dir_display)).print()

        deleted, failed = 0, 0
        try:
            for item in list(dir_path.iterdir()):
                try:
                    if item.is_file():
                        item.unlink()
                        deleted += 1
                    elif item.is_dir():
                        import shutil

                        shutil.rmtree(item, ignore_errors=True)
                        if not item.exists():
                            deleted += 1
                        else:
                            failed += 1
                except (PermissionError, OSError):
                    failed += 1

        except (PermissionError, OSError) as exc:
            failures.append(f"Cannot access {dir_path}: {exc}")

        del_suffix = "" if deleted == 1 else "s"
        S("    ", S.GREEN("✓"), " Deleted ", S.BOLD(str(deleted)), f" item{del_suffix}").print()
        if failed:
            fail_suffix = "" if failed == 1 else "s"
            S(
                "    ",
                S.YELLOW(f"⚠ {failed} item{fail_suffix} could not be deleted ", S.DIM("(locked / in use)")),
            ).print()

    return failures


# ********************************************************** DISPLAY **********************************************************


def show_summary(  # ruff:ignore[complex-structure]
    reg_app_path_issues: list[dict[str, Any]],
    reg_unins_issues: list[dict[str, Any]],
    reg_startup_issues: list[dict[str, Any]],
    env_issues: dict[str, Any],
    shortcut_issues: list[dict[str, Any]],
    temp_info: dict[str, Any],
    selected: dict[str, bool],
) -> None:
    """Show a detailed summary of what will be cleaned."""

    total_reg_issues = len(reg_app_path_issues) + len(reg_unins_issues) + len(reg_startup_issues)
    total_env_issues = len(env_issues.get("user", [])) + len(env_issues.get("system", []))
    total_sc_issues = sum(len(loc["broken_shortcuts"]) for loc in shortcut_issues)
    total_temp_issues = len(temp_info.get("dirs", []))
    total_issues = total_reg_issues + total_env_issues + total_sc_issues + total_temp_issues

    if total_issues == 0:
        S.GREEN("\nNo issues found! Your system paths look clean. Nothing to do.\n").print()
        raise SystemExit(0)

    title: tuple[TextRenderable, TextRenderable] = (
        (S.BOLD | S.hex("000") | S.BG.BR.MAGENTA)("  Cleanup Summary  "),
        (S.BR.MAGENTA | S.BG.BLACK)(f"  Found {total_issues} issues  "),
    )

    S(
        "\n",
        (S.BR.MAGENTA("▄" * len(title[0].raw)), S.BLACK("▄" * len(title[1].raw))),
        (*title,),
        (S.BR.MAGENTA("▀" * len(title[0].raw)), S.BLACK("▀" * len(title[1].raw))),
        "",
        sep="\n",
    ).print()

    if selected.get("registry") and (reg_unins_issues or reg_app_path_issues or reg_startup_issues):
        S("", S.BOLD("Registry entries to delete: "), S.DIM(f"({total_reg_issues} total)\n")).print()

        for issue in reg_app_path_issues:
            S(
                "  ",
                S.RED("✗"),
                " ",
                (S.BOLD | S.MAGENTA)(issue["subkey"]),
                " ",
                S.BR.MAGENTA(f"({hive_name(issue['hive'])}\\…\\App Paths)"),
            ).print()
            S.DIM(f"    → {issue['broken_path']}").print()

        for issue in reg_unins_issues:
            count = len(issue["broken_values"])
            suffix = "" if count == 1 else "s"
            S(
                "  ",
                S.RED("✗"),
                " ",
                (S.BOLD | S.MAGENTA)(issue["display_name"]),
                " ",
                S.BR.MAGENTA(f"({hive_name(issue['hive'])}\\…\\{issue['subkey']})"),
                f" — {count} broken path{suffix}:",
            ).print()

            for val_name, val_data in issue["broken_values"]:
                path_val = extract_path_from_value(val_data)
                S("    ", (S.DIM | S.BR.MAGENTA)(val_name), f" → {path_val or val_data}").print()

        for issue in reg_startup_issues:
            tail = issue["path"].rsplit("\\", 1)[-1]
            S(
                "  ",
                S.RED("✗"),
                " ",
                (S.BOLD | S.MAGENTA)(issue["value_name"]),
                " ",
                S.BR.MAGENTA(f"({hive_name(issue['hive'])}\\…\\{tail})"),
            ).print()
            S.DIM(f"    → {issue['value_data']}").print()

        print()

    if selected.get("envvars") and (env_issues.get("user") or env_issues.get("system")):
        S("", S.BOLD("Environment variables to clean: "), S.DIM(f"({total_env_issues} total)\n")).print()

        for scope in ("user", "system"):
            for issue in env_issues.get(scope, []):
                name = issue["name"]
                broken = issue["broken_paths"]
                original = issue["original_value"]

                if ";" in original:
                    count = len(broken)
                    suffix = "" if count == 1 else "s"
                    S(
                        "  ",
                        (S.BOLD | S.CYAN)(name),
                        " ",
                        S.BR.CYAN(f"({scope})"),
                        f" — remove {count} broken path{suffix}:",
                    ).print()

                    for broken_path in broken:
                        S("    ", S.RED("✗"), " ", (S.DIM | S.BR.CYAN)(broken_path)).print()

                else:
                    S(
                        "  ",
                        (S.BOLD | S.CYAN)(name),
                        " ",
                        S.BR.CYAN(f"({scope})"),
                        " — ",
                        S.RED("delete entire variable"),
                    ).print()
                    S.DIM(f"    → {original}").print()

        print()

    if selected.get("shortcuts") and shortcut_issues:
        S("", S.BOLD("Broken shortcuts to delete: "), S.DIM(f"({total_sc_issues} total)\n")).print()

        for location in shortcut_issues:
            count = len(location["broken_shortcuts"])
            suffix = "" if count == 1 else "s"
            S(
                "  ",
                (S.BOLD | S.BLUE)(location["label"]),
                f" — remove {count} broken shortcut{suffix}:",
            ).print()

            for sc in location["broken_shortcuts"]:
                S("    ", S.RED("✗"), " ", (S.DIM | S.BR.BLUE)(sc["lnk_path"].name), f" → {sc['target']}").print()

        print()

    if selected.get("temp") and temp_info.get("dirs"):
        S("", S.BOLD("Temp directories to clean: "), S.DIM(f"({total_temp_issues} total)\n")).print()

        for dir_item in temp_info["dirs"]:
            S(
                "  ",
                S.YELLOW("⟳ ", S.BOLD(dir_item["label"])),
                S.DIM(f" — {dir_item['file_count']} files, "),
                S.BOLD(format_size(dir_item["size_bytes"])),
            ).print()

        print()


# *********************************************************** MAIN ************************************************************


def choose_options() -> dict[str, bool]:
    """Let the user choose which cleanup options to run."""

    S.BOLD("\nChoose what to clean:\n").print()
    options = [
        ("registry", "Registry?             "),
        ("envvars", "Environment variables?"),
        ("shortcuts", "Broken shortcut files?"),
        ("temp", "Temp files?           "),
    ]

    if not HAS_WIN32COM:
        (S.DIM | S.YELLOW)("  ⚠ pywin32 not installed — shortcut scanning disabled\n").print()

    selected: dict[str, bool] = {}

    for key, label in options:
        if key == "shortcuts" and not HAS_WIN32COM:
            selected[key] = False
            continue
        answer = xx.console.confirm(f"  {label} ", default_is_yes=True)
        selected[key] = answer

    return selected


def main() -> None:  # ruff:ignore[complex-structure]
    # Handle restore mode:
    if ARGS.restore.exists or ARGS.path.exists:
        restore_path_str = (ARGS.restore.val(default="") or ARGS.path.val(default="")).strip()
        if not restore_path_str:
            usage_str = S(
                "Please provide a path to the backup JSON file.\n  Usage: ",
                S.BR.GREEN("x-clean "),
                S.BR.BLUE("--restore "),
                S.BR.CYAN("path/to/backup.json"),
            )
            xx.console.fail(
                usage_str,
                start="\n",
                end="\n\n",
                exit_code=1,
            )
            return
        restore_env_vars(Path(restore_path_str))
        return

    title = (S.INVERSE | S.BG.hex("000"))(S.BOLD("  Windows "), "System Paths Cleaner  ")
    S("", "▄" * len(title.raw), title, "▀" * len(title.raw), sep="\n").print()

    xx.console.box(
        "This tool scans for and removes broken system paths.",
        S(S.DIM("→"), " Backups are created before any modifications."),
        S(S.DIM("→"), " No actions are taken without confirmation."),
        border_style=S.DIM | S.YELLOW,
        default_color=S.YELLOW,
    )

    if not xx.system.is_elevated():
        S.YELLOW("\n⚠ Not running as Administrator. Some operations may fail.").print()
        (S.DIM | S.YELLOW)("  System-level registry and env var changes require elevation.").print()

    # [1] Choose cleanup options:
    selected = choose_options()

    if not any(selected.values()):
        xx.console.exit("Nothing selected.", start="\n", end="\n\n")

    # [2] Create backups:
    title = (S.BOLD | S.hex("000") | S.BG.BR.GREEN)("  Creating Backups  ")
    S("\n", S.BR.GREEN("▄" * len(title.raw)), title, S.BR.GREEN("▀" * len(title.raw)), "", sep="\n").print()

    backup_dir = create_backup_dir()
    backup_ok = True

    if selected.get("registry"):
        S.BOLD("Backing up registry keys...").print()
        if not backup_registry(backup_dir):
            backup_ok = False

    if selected.get("envvars"):
        S.BOLD("\nBacking up environment variables...").print()
        if not backup_env_vars(backup_dir):
            backup_ok = False

    if not backup_ok:
        backup_link = (S.DIM | S.BR.RED | S.link(backup_dir))(f"{backup_dir.parent.name}/{backup_dir.name}")
        xx.console.fail(
            S(S.RED("Some backups failed! Aborting for safety.\n  "), "Backup directory: ", backup_link),
            start="\n",
            end="\n\n",
            exit_code=1,
        )

    backup_link = (S.BR.GREEN | S.link(backup_dir))(f"{backup_dir.parent.name}/{backup_dir.name}")
    S("\n", (S.BOLD | S.GREEN)("✓ Backups saved to: "), backup_link).print()

    # [3] Scan for issues:
    refresh_env_from_registry()

    reg_app_path_issues: list[dict[str, Any]] = []
    reg_unins_issues: list[dict[str, Any]] = []
    reg_startup_issues: list[dict[str, Any]] = []
    env_issues: dict[str, Any] = {"user": [], "system": []}
    shortcut_issues: list[dict[str, Any]] = []
    temp_info: dict[str, Any] = {"dirs": []}

    with Throbber().context("Scanning for issues") as update_label:
        if selected.get("registry"):
            update_label("Scanning registry App Paths")
            reg_app_path_issues = scan_registry_app_paths()
            update_label("Scanning registry uninstall entries")
            reg_unins_issues = scan_registry_unins_paths()
            update_label("Scanning registry Run/RunOnce")
            reg_startup_issues = scan_registry_startup_paths()

        if selected.get("envvars"):
            update_label("Scanning environment variables")
            env_issues = scan_env_vars()

        if selected.get("shortcuts"):
            update_label("Scanning shortcut files")
            shortcut_issues = scan_shortcuts()

        if selected.get("temp"):
            update_label("Scanning temp directories")
            temp_info = scan_temp_files()

    # [4] Show summary and confirm:
    show_summary(reg_app_path_issues, reg_unins_issues, reg_startup_issues, env_issues, shortcut_issues, temp_info, selected)

    if not xx.console.confirm("\nProceed with cleanup?", default_is_yes=False):
        S("\n", (S.DIM | S.BR.MAGENTA)("✗ ", S.ITALIC("Cleanup canceled.")), "\n").print()
        raise SystemExit(0)

    # [5] Execute cleanup:
    S("\n\n\n", (S.BOLD | S.INVERSE | S.BR.BLUE | S.BG.hex("000"))(" EXECUTING CLEANUP "), "\n").print()

    all_failures: list[str] = []

    if selected.get("registry") and (reg_unins_issues or reg_app_path_issues or reg_startup_issues):
        all_failures.extend(execute_registry_cleanup(reg_app_path_issues, reg_unins_issues, reg_startup_issues))
    if selected.get("envvars") and (env_issues.get("user") or env_issues.get("system")):
        all_failures.extend(execute_env_cleanup(env_issues))
    if selected.get("shortcuts") and shortcut_issues:
        all_failures.extend(execute_shortcut_cleanup(shortcut_issues))
    if selected.get("temp") and temp_info.get("dirs"):
        all_failures.extend(execute_temp_cleanup(temp_info))

    # [6] Final report:
    print()

    if not all_failures:
        backup_link = (S.BR.GREEN | S.link(backup_dir))(f"{backup_dir.parent.name}/{backup_dir.name}")

        S(
            "\n",
            (S.BOLD | S.GREEN)("✓ Cleanup completed successfully!"),
            "\n\n  ",
            S.DIM("Backups are at: ", backup_link),
            "\n\n",
        ).print()

    else:
        suffix = "" if (count := len(all_failures)) == 1 else "s"
        backup_link = (S.BR.GREEN | S.link(backup_dir))(f"{backup_dir.parent.name}/{backup_dir.name}")

        S(
            "\n",
            S.BOLD(S.RED("✓"), " Cleanup completed with ", S.RED(str(count)), f" failure{suffix}:\n"),
        ).print()

        for msg in all_failures:
            S("  ", S.RED("✗"), " ", S.BR.RED(msg)).print()

        S(
            "\n\n  ",
            S.DIM("Backups are at: ", backup_link),
            "\n\n",
        ).print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="System Cleaner",
        subtitle="Clean broken registry entries, env vars, shortcuts & more",
        controls=[("Ctrl+C", "Cancel and exit")],
        examples=[
            ('{cmd} --restore="path/to/env_vars_backup.json"', "Restore env vars from backup"),
        ],
        epilog=S(
            S.BOLD("What it cleans:"),
            ("  ", S.MAGENTA("1. "), "Registry ", S.DIM("(app paths, uninstall entries, startup entries)")),
            ("  ", S.MAGENTA("2. "), "Environment variables containing non-existent paths"),
            ("  ", S.MAGENTA("3. "), "Broken shortcut (.lnk) files ", S.DIM("(start menu, startup, desktop)")),
            ("  ", S.MAGENTA("4. "), "Temporary files ", S.DIM("(user temp, system temp, crash dumps)")),
            sep="\n",
        ),
    )

    args.add_arg("path", required=False, help="Backup file path to restore")
    args.add_opt({"-r", "--restore"}, expects_value="PATH", help="Restore env vars from a backup JSON file")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        S("\n", (S.DIM | S.BR.MAGENTA)("✗ ", S.ITALIC("Canceled by user.")), "\n").print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

#!/usr/bin/env python3
# x-tools:file[update]

"""
Force delete files or directories, even if they are locked by processes.
"""

import contextlib
import os
import platform
import shutil
import subprocess
import time
from contextlib import suppress
from pathlib import Path
import psutil
import xulbux as xx
from xulbux import ArgumentParser, S

# ************************************ CRITICAL PROCESSES THAT SHOULD NEVER BE TERMINATED *************************************

PROTECTED_PROCESSES_WINDOWS = {
    "csrss.exe",
    "dwm.exe",
    "lsass.exe",
    "services.exe",
    "smss.exe",
    "svchost.exe",
    "system",
    "wininit.exe",
    "winlogon.exe",
}
PROTECTED_PROCESSES_MACOS = {
    "configd",
    "coreaudiod",
    "Dock",
    "Finder",
    "kernel_task",
    "loginwindow",
    "SystemUIServer",
    "UserEventAgent",
    "WindowServer",
}
PROTECTED_PROCESSES_UNIX = {
    "bash",
    "cron",
    "dbus-daemon",
    "fish",
    "init",
    "kernel",
    "kthreadd",
    "launchd",
    "login",
    "migration",
    "NetworkManager",
    "rcu_sched",
    "rsyslogd",
    "sh",
    "sshd",
    "systemd-journald",
    "systemd-udevd",
    "systemd",
    "watchdog",
    "zsh",
}


def get_protected_processes() -> set[str]:
    """Get the appropriate protected processes list for the current OS."""

    if (system := platform.system()) == "Windows":
        return PROTECTED_PROCESSES_WINDOWS
    elif system == "Darwin":  # macOS
        return PROTECTED_PROCESSES_UNIX | PROTECTED_PROCESSES_MACOS
    else:  # Unix-like
        return PROTECTED_PROCESSES_UNIX


def take_ownership_windows(path: Path) -> bool:
    """Take ownership of a file/directory on Windows."""

    S.BOLD("Taking ownership of ", S.BR.CYAN(path.name), "...").print()

    try:
        # Take ownership using `takeown`:
        result = subprocess.run(
            ["takeown", "/F", str(path)] + (["/R", "/D", "Y"] if path.is_dir() else []),
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=(subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0),
        )

        if result.returncode != 0:
            S.YELLOW(S.BOLD("⚠ takeown failed:\n"), "  ", result.stderr.strip().replace("\n", "\n  ")).print()
            return False

        # Grant full control using `icacls`:
        result = subprocess.run(
            ["icacls", str(path), "/grant", f"{os.getlogin()}:F", "/C", "/Q"] + (["/T"] if path.is_dir() else []),
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode != 0:
            S.YELLOW(S.BOLD("⚠ icacls failed:\n"), "  ", result.stderr.strip().replace("\n", "\n  ")).print()
            return False

        S.GREEN("✓ Successfully took ownership").print()
        return True

    except subprocess.TimeoutExpired:
        (S.BOLD | S.YELLOW)("⚠ takeown/icacls timed out, some ownership may have been granted").print()
        return True
    except Exception as exc:
        S.RED(S.BOLD("✗ Error taking ownership:\n"), "  ", str(exc).replace("\n", "\n  ")).print()
        return False


def remove_attributes_windows(path: Path) -> bool:
    """Remove file attributes on Windows (readonly, system, hidden)."""

    S.BOLD("Removing attributes from ", S.BR.CYAN(path.name), "...").print()

    try:
        result = subprocess.run(
            ["attrib", "-R", "-S", "-H", str(path)] + (["/S", "/D"] if path.is_dir() else []),
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode != 0:
            S.YELLOW(S.BOLD("⚠ attrib failed:\n"), "  ", result.stderr.strip().replace("\n", "\n  ")).print()
            return False

        S.GREEN("✓ Successfully removed attributes").print()
        return True

    except subprocess.TimeoutExpired:
        (S.BOLD | S.YELLOW)("⚠ attrib timed out, some attributes may have been cleared").print()
        return True
    except Exception as exc:
        S.RED(S.BOLD("✗ Error removing attributes:\n"), "  ", str(exc).replace("\n", "\n  ")).print()
        return False


def change_permissions_unix(path: Path) -> bool:
    """Change permissions on Unix systems."""

    S.BOLD("Changing permissions for ", S.BR.CYAN(path.name), "...").print()

    try:
        # Try to make everything writable:
        result = subprocess.run(
            ["chmod", "-R", "777", str(path)] if path.is_dir() else ["chmod", "777", str(path)], capture_output=True, text=True
        )

        if result.returncode != 0:
            S.YELLOW(S.BOLD("⚠ chmod failed:\n"), "  ", result.stderr.strip().replace("\n", "\n  ")).print()
            return False

        S.GREEN("✓ Successfully changed permissions").print()
        return True

    except Exception as exc:
        S.RED(S.BOLD("✗ Error changing permissions:\n"), "  ", str(exc).replace("\n", "\n  ")).print()
        return False


def unlock_file_macos(path: Path) -> bool:
    """Unlock files on macOS using `chflags`."""

    S.BOLD("Unlocking ", S.BR.CYAN(path.name), " on macOS...").print()

    try:
        # Remove all flags including user immutable and system immutable:
        result = subprocess.run(
            ["chflags", "-R", "nouchg,nouappnd,nosappnd,nosunlnk", str(path)]
            if path.is_dir()
            else ["chflags", "nouchg,nouappnd,nosappnd,nosunlnk", str(path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            S.YELLOW(S.BOLD("⚠ chflags failed:\n"), "  ", result.stderr.strip().replace("\n", "\n  ")).print()
            return False

        S.GREEN("✓ Successfully unlocked file").print()
        return True

    except Exception as exc:
        S.RED(S.BOLD("✗ Error unlocking file:\n"), "  ", str(exc).replace("\n", "\n  ")).print()
        return False


def try_advanced_deletion_techniques(path: Path) -> bool:
    """Try advanced OS-specific deletion techniques."""

    system = platform.system()
    success = False

    if system == "Windows":
        if remove_attributes_windows(path):
            success = True
        if take_ownership_windows(path):
            success = True

    elif system == "Darwin":  # macOS
        if unlock_file_macos(path):
            success = True
        if change_permissions_unix(path):
            success = True

    else:  # Unix-like
        if change_permissions_unix(path):
            success = True

    return success


def find_processes_using_path(path: Path) -> list[psutil.Process]:
    """Find all processes that have handles to the given path."""

    processes: list[psutil.Process] = []
    system = platform.system()
    path = path.resolve()

    for proc in psutil.process_iter(["pid", "name", "open_files", "cwd", "exe"]):
        try:
            # Check open files:
            if proc.info["open_files"]:
                for file_item in proc.info["open_files"]:
                    file_path = file_item.path if hasattr(file_item, "path") else str(file_item)
                    if (path_str := str(path).lower()) in (file_str := file_path.lower()) or file_str in path_str:
                        processes.append(proc)
                        break

            # On Unix systems, also check current working directory:
            if system != "Windows":
                with suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                    if (
                        (path_str := str(path).lower()) in (cwd_str := proc.cwd().lower()) or cwd_str in path_str
                    ) and proc not in processes:
                        processes.append(proc)

        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            continue

    return processes


def is_protected_process(proc: psutil.Process) -> bool:
    """Check if a process is in the protected list."""

    try:
        name = proc.name().lower()
        protected_set = get_protected_processes()

        # Check exact name match:
        if name in protected_set:
            return True

        # For Unix systems, also check without extension and base name:
        if platform.system() != "Windows":
            base_name = Path(name).name
            if base_name in protected_set:
                return True

        # Check if it's PID 1 (init/systemd/launchd); never terminate this:
        if proc.pid == 1:
            return True

        # On Unix, protect processes owned by root running critical services:
        if platform.system() != "Windows":
            with suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                if proc.username() == "root" and proc.pid < 1000:
                    return True

        return False
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return True  # Err on the side of caution.


def terminate_process(proc: psutil.Process) -> bool:
    """Attempt to terminate a process."""

    try:
        S(
            "  Terminating ",
            S.MAGENTA(proc.name().strip()),
            " ",
            S.DIM("(PID ", S.MAGENTA(str(proc.pid)), ")"),
            "...",
        ).print()
        proc.terminate()
        proc.wait(timeout=5)
        return True

    except psutil.TimeoutExpired:
        S(
            (S.BOLD | S.YELLOW)("  ⚠ Process didn't terminate gracefully, killing:\n"),
            "    ",
            S.MAGENTA(proc.name().strip()),
            " ",
            (S.DIM | S.YELLOW)("(PID ", S.MAGENTA(str(proc.pid)), ")"),
        ).print()
        try:
            proc.kill()
            return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return False

    except (psutil.AccessDenied, psutil.NoSuchProcess):
        S(
            (S.BOLD | S.RED)("  ✗ Access denied or process no longer exists:\n"),
            "    ",
            S.MAGENTA(proc.name().strip()),
            " ",
            S.DIM("(PID ", S.MAGENTA(str(proc.pid)), ")"),
        ).print()
        return False


def attempt_deletion(path: Path) -> bool:
    """Attempt to delete a path."""

    S.BOLD("Deleting ", S.BR.CYAN(path.name), "...").print()

    try:
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    except PermissionError:
        (S.BOLD | S.YELLOW)("⚠ Permission denied!").print()
    except OSError as exc:
        # On Unix systems, we might get different errors:
        if platform.system() != "Windows":
            S.YELLOW(S.BOLD("⚠ Deletion blocked:\n"), "  ", str(exc).replace("\n", "\n  ")).print()
        else:
            S.RED(S.BOLD("✗ Error during deletion:\n"), "  ", str(exc).replace("\n", "\n  ")).print()
    except Exception as exc:
        S.RED(S.BOLD("✗ Error during deletion:\n"), "  ", str(exc).replace("\n", "\n  ")).print()

    return not path.exists()


def force_delete(path: Path) -> bool:  # ruff:ignore[complex-structure]
    """Force delete a file or directory, terminating processes if needed."""

    print()

    # Try to delete without terminating processes:
    if attempt_deletion(path):
        S(
            (S.BOLD | S.GREEN)("✓ Successfully deleted: "),
            (S.BR.CYAN | S.link(f"file:///{path.resolve()}"))(path.name),
            "\n",
        ).print()
        return True

    # First try advanced deletion techniques:
    S.YELLOW("  Trying advanced deletion techniques...").print()

    if try_advanced_deletion_techniques(path):
        time.sleep(0.5)
        if attempt_deletion(path):
            S(
                "\n",
                (S.BOLD | S.GREEN)("✓ Successfully deleted: "),
                (S.BR.CYAN | S.link(f"file:///{path.resolve()}"))(path.name),
                "\n",
            ).print()
            return True

    # Now try to find processes using the path:
    S.YELLOW("  Searching for processes using this path...").print()
    processes = find_processes_using_path(path)

    if processes:
        count = len(processes)
        suffix = "" if count == 1 else "es"
        S.BOLD("Found ", S.MAGENTA(str(count)), f" process{suffix} using this path:").print()
        for proc in processes:
            with contextlib.suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                S("  ", S.MAGENTA(proc.name()), " ", S.DIM("(PID ", S.MAGENTA(str(proc.pid)), ")")).print()

        # Check for protected processes:
        protected = [proc for proc in processes if is_protected_process(proc)]
        if protected:
            (S.BOLD | S.RED)("\n⯃ The following critical system processes are using this path:").print()
            for proc in protected:
                with contextlib.suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                    S("  ", S.MAGENTA(proc.name()), " ", S.DIM("(PID ", S.MAGENTA(str(proc.pid)), ")")).print()
            S.RED("  These processes will ", S.BOLD("NOT"), " be terminated for system safety.\n").print()
            return False

        # Terminate non-protected processes:
        S.BOLD("Terminating processes...").print()
        terminated: list[psutil.Process] = []
        for proc in processes:
            if terminate_process(proc):
                terminated.append(proc)

        if not terminated:
            S.RED("Failed to terminate any processes.\n").print()
        else:
            time.sleep(1)
            if attempt_deletion(path):
                S(
                    "\n",
                    (S.BOLD | S.GREEN)("✓ Successfully deleted: "),
                    (S.BR.CYAN | S.link(f"file:///{path.resolve()}"))(path.name),
                    "\n",
                ).print()
                return True

    # Still failed; give up :(
    (S.BOLD | S.RED)("\n✗ Failed to delete even after trying all techniques :(\n").print()

    if not xx.system.is_elevated():
        if platform.system() == "Windows":
            (S.DIM | S.BLUE)("ⓘ ", S.ITALIC("Try running with Administrator privileges.\n")).print()
        else:
            (S.DIM | S.BLUE)("ⓘ ", S.ITALIC("Try running with sudo for elevated privileges.\n")).print()
    else:
        (S.DIM | S.BLUE)(
            "ⓘ ",
            S.ITALIC("The file/directory may be protected by the system or in use by a kernel-level process.\n"),
        ).print()

    return False


def path_validator(path: str) -> str | None:
    """Validate the input path."""

    if not Path(path).exists():
        max_width = xx.console.get_width() - 23
        truncated_path = path if (path_len := len(path)) <= max_width else f"…{path[path_len - (max_width - 1) :]}"
        return str(S("Path ", S.ITALIC(truncated_path), " doesn't exist."))


def main() -> None:
    """Main force remove entry point."""

    S("\n", (S.BOLD | S.BG.hex("000"))(f" {platform.system()} ", S.INVERSE(" FORCE DELETE UTILITY "))).print()
    xx.console.box(
        "This will terminate processes if needed.",
        "Critical system processes are protected.",
        border_style=S.DIM | S.YELLOW,
        default_color=S.YELLOW,
    )

    if not xx.system.is_elevated():
        if platform.system() == "Windows":
            S.YELLOW("\n⚠ Not running as Administrator. Some operations may fail.").print()
        else:
            S(
                S.YELLOW("\n⚠ Not running as root. Some operations may fail.\n"),
                (S.DIM | S.YELLOW)("  Consider running: "),
                (S.BOLD | S.BR.WHITE)("sudo"),
                " ",
                S.WHITE("python"),
                " ",
                S.BR.GREEN("x-rm"),
                " ",
                S.BR.CYAN("<path>"),
            ).print()

    target_path_str = ARGS.path.val(default="") or ARGS.yolo_mode.val(default="")
    if not target_path_str:
        target_path_str = xx.console.input(S("\n", S.BOLD("Path to file/directory to delete > ")), validator=path_validator)

    if not (target_path := Path(target_path_str)).exists():
        xx.console.fail(S("Path ", S.BR.CYAN(str(target_path)), " does not exist!"), start="\n", end="\n\n", exit_code=1)

    if not ARGS.yolo_mode.exists and not xx.console.confirm(
        S("\n", S.BOLD("Are you sure you want to delete "), (S.BR.CYAN | S.BG.BLACK)(target_path.name), S.BOLD("?")),
        default_is_yes=False,
    ):
        xx.console.exit("Deletion aborted.", start="\n", end="\n\n")

    raise SystemExit(0 if force_delete(target_path) else 1)


if __name__ == "__main__":
    args = ArgumentParser(
        title="Force Remove",
        subtitle="Delete files/directories even if they are locked",
        controls=[("Ctrl+C", "Cancel and exit")],
        examples=[
            ('{cmd} "/path/to/directory"', "Delete a directory"),
            ('{cmd} -y="/path/to/file.txt"', "Delete a file, skipping confirmation"),
        ],
    )

    args.add_arg("path", required=False, help="The path to the file/directory to delete")
    args.add_opt(
        {"-y", "--yolo"},
        "yolo_mode",
        expects_value="PATH",
        help=("Skip confirmation prompt for ", S.BR.BLUE("PATH"), " deletion"),
    )

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        (S.BOLD | S.RED)("✗ Canceled by user.\n").print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

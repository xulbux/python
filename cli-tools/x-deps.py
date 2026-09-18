#!/usr/bin/env python3
# x-tools:file[update]

"""
List all library dependencies imported across Python files in the script directory.
Filters out local project modules, showing only installable packages.
"""

import re
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING
import xulbux as xx
from xulbux import ArgumentParser, S, Throbber

# Make the `_shared` package (cli-tools/_shared) importable when running this script directly:
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared.helpers import print_json

if TYPE_CHECKING:
    from ._shared.helpers import print_json  # ruff:ignore[runtime-import-in-type-checking-block]


def extract_imports(file_path: Path) -> set[str]:
    """Extract all imported module names from a Python file."""

    imports: set[str] = set()
    import_pattern = re.compile(r"^\s*(?:from\s+(\S+)|import\s+(\S+))", re.MULTILINE)

    with suppress(Exception), open(file_path, encoding="utf-8") as file:
        content = file.read()

        # Remove docstrings and comments before processing.
        # Triple-quoted strings (docstrings):
        content = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", content)

        # Single/double quoted strings:
        content = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', "", content)

        # Comments (lines starting with `#`):
        content = re.sub(r"#.*$", "", content, flags=re.MULTILINE)

        for match in import_pattern.finditer(content):
            module = match.group(1) or match.group(2)

            # Skip relative imports (starting with `.`):
            if module.startswith("."):
                continue

            # Add top-level module name:
            imports.add(module.split(".")[0])

    return imports


def get_local_module_names(directory: Path) -> set[str]:
    """Collect all local Python module names (file stems and package dirs) in the tree."""

    names: set[str] = set()

    with suppress(PermissionError):
        for item in directory.rglob("*"):
            if item.is_file() and item.suffix in {".py", ".pyw"}:
                names.add(item.stem)
            elif item.is_dir() and (item / "__init__.py").exists():
                names.add(item.name)

    return names


def get_all_modules(directory: Path, recursive: bool = False, external_only: bool = False) -> dict[str, list[str]]:
    """Get all modules used across Python files, grouped by module name."""

    module_usage: dict[str, list[str]] = {}

    if not directory.is_dir():
        raise ValueError(f"Directory not found: {directory}")

    local_modules = get_local_module_names(directory)

    def scan_directory(dir_path: Path, base_path: Path | None = None) -> None:
        """Scan a directory for Python files and extract imports."""

        if base_path is None:
            base_path = dir_path

        with suppress(PermissionError):
            for full_path in dir_path.iterdir():
                if full_path.is_file() and full_path.suffix in {".py", ".pyw"}:
                    for module in extract_imports(full_path):
                        if module in local_modules:
                            continue
                        if external_only and module in sys.stdlib_module_names:
                            continue
                        if module not in module_usage:
                            module_usage[module] = []
                        module_usage[module].append(full_path.relative_to(base_path).as_posix())
                elif recursive and full_path.is_dir():
                    scan_directory(full_path, base_path)

    scan_directory(directory)
    return module_usage


def _format_install_error(module: str, raw_error: str) -> S:
    """Format pip install error output with styled vertical bars."""

    header = S.BR.RED("✗ Failed to install ", S.BOLD(module), ":")
    bar = (S.DIM | S.RED)("│ ")
    clean_lines = [re.sub(r"(?i)^(?:error:\s*|\[error\]\s*)?(.*)", r"\1", line) for line in raw_error.splitlines()]
    error_lines = [S(bar, (S.DIM | S.BR.RED)(line)) for line in clean_lines]

    return S(header, "\n", S("\n").join(error_lines))


def show_and_install_modules(  # ruff:ignore[complex-structure]
    modules: dict[str, list[str]], external_only: bool, install: bool = False, *, raw: bool = False
) -> None:
    """Display detected modules and optionally install missing packages.\n
    ----------------------------------------------------------------------------------------------------
    *   `modules` – Mapping of module names to files importing them.
    *   `external_only` – Whether to filter for non-standard library modules only.
    *   `install` – Whether to prompt for and install missing packages via pip.
    *   `raw` – Whether to render plain text without ANSI colors or title banners."""

    if raw:
        if ARGS.list.exists:
            print("\n".join(sorted(modules.keys())))
        else:
            for module, files in sorted(modules.items()):
                usage_count = len(files)
                file_suffix = "s" if usage_count != 1 else ""
                print(f"{module} (used in {usage_count} file{file_suffix}): {', '.join(sorted(files))}")

    elif ARGS.list.exists:
        title_start = "Installing" if install else "Found"
        category = "external modules" if external_only else "modules"
        title = (S.INVERSE | S.BG.hex("000"))(f"  {title_start} ", S.BOLD(str(len(modules))), f" {category}  ")

        S(
            "▄" * len(title.raw),
            title,
            "▀" * len(title.raw),
            "",
            (S.BOLD | S.BR.CYAN)("\n".join(sorted(modules.keys()))),
            "",
            sep="\n",
        ).print()

    else:
        title_start = "Installing" if install else "Found"
        category = "external modules" if external_only else "modules"
        title = (S.INVERSE | S.BG.hex("000"))(f"  {title_start} ", S.BOLD(str(len(modules))), f" {category}  ")
        console_width = xx.console.get_width()
        num_width = len(str(len(modules)))
        lines: list[S] = []

        for i, (module, files) in enumerate(sorted(modules.items()), 1):
            usage_count = len(files)
            file_suffix = "s" if usage_count != 1 else ""
            prefix = S(
                " ",
                (S.ITALIC | S.DIM | S.BR.CYAN)(f"{i:>{num_width}}"),
                "  ",
                (S.BOLD | S.BR.CYAN)(module),
                " ",
                S.DIM(f"used in {usage_count} file{file_suffix}"),
            )
            prefix_len = len(prefix)

            if usage_count <= 5:
                file_paths = ", ".join(sorted(files))
                if (prefix_len + 1 + len(file_paths)) > console_width:
                    file_part = f" {file_paths[: console_width - (prefix_len + 2)]}…"
                else:
                    file_part = f" {file_paths}"
                lines.append(S(prefix, file_part))
            else:
                file_paths = ", ".join(sorted(files)[:3])
                overflow_part = S(", ", S.DIM(f"+{usage_count - 3} more"))
                overflow_len = len(overflow_part)
                if (prefix_len + 1 + len(file_paths) + overflow_len) > console_width:
                    available = console_width - (prefix_len + overflow_len + 2)
                    file_part = f" {file_paths[:available]}…"
                else:
                    file_part = f" {file_paths}"
                lines.append(S(prefix, file_part, overflow_part))

        S(
            "▄" * len(title.raw),
            title,
            "▀" * len(title.raw),
            "",
            S("\n").join(lines),
            "",
            sep="\n",
        ).print()

    # ************************ INSTALLATION *************************

    if not install:
        return
    if not xx.console.confirm("Proceed with installation?"):
        (S.ITALIC | S.DIM)("\nInstallation cancelled.\n").print()
        return

    print()
    failed_modules: list[str] = []

    for module in sorted(modules):
        with Throbber(
            label=S("Installing ", S.BOLD(module)),
            format=[(S.DIM | S.BR.CYAN)("{a}"), S.BR.CYAN("{l}")],
            frames=("⠴", "⠦", "⠖", "⠲"),
            interval=0.1,
        ).context():
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", module],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 MINUTE TIMEOUT PER MODULE
                )

                if result.returncode == 0:
                    S.BR.GREEN("✓ Installed ", S.BOLD(module)).print()
                else:
                    _format_install_error(module, result.stderr).print()
                    failed_modules.append(module)
            except subprocess.TimeoutExpired:
                S.BR.RED("✗ Timed out installing ", S.BOLD(module)).print()
                failed_modules.append(module)
            except Exception as exc:
                _format_install_error(module, str(exc)).print()
                failed_modules.append(module)

    print()
    if failed_modules:
        count = len(failed_modules)
        suffix = "" if count == 1 else "s"
        (S.BOLD | S.YELLOW)(f"⚠ Failed to install {count} module{suffix}:").print()
        for module in failed_modules:
            S.BR.YELLOW(S.DIM("•"), f" {module}").print()
        print()
    else:
        (S.BOLD | S.BR.GREEN)("All modules installed successfully!\n").print()


def main() -> None:
    """Scan directory for Python dependencies and display or install them."""

    if not ARGS.raw_output.exists:
        print()

    external_only = bool(ARGS.external or ARGS.install)
    directory = ARGS.path.val(Path, xx.fs.get_script_dir()).expanduser().resolve()

    with Throbber().context():
        modules = get_all_modules(directory=directory, recursive=ARGS.recursive.exists, external_only=external_only)

    if not modules:
        if ARGS.raw_output.exists:
            print("No external modules found" if external_only else "No modules found")
        elif external_only:
            (S.ITALIC | S.DIM)("No external modules found\n").print()
        else:
            (S.ITALIC | S.DIM)("No modules found\n").print()
        return

    if not ARGS.install.exists and ARGS.as_json.exists:
        if ARGS.list.exists:
            json_data = sorted(modules.keys())
        else:
            json_data = {module: sorted(files) for module, files in sorted(modules.items())}
        print_json(json_data, raw=ARGS.raw_output.exists)

    else:
        show_and_install_modules(modules, external_only, ARGS.install.exists, raw=ARGS.raw_output.exists)


if __name__ == "__main__":
    args = ArgumentParser(
        title="Deps",
        subtitle="List all library dependencies across scripts",
        examples=[
            ("{cmd}", "Scan current script directory"),
            ("{cmd} path/to/project -e", "Scan project for external dependencies only"),
            ("{cmd} -R -l", "Recursive scan, output flat package list"),
            ("{cmd} -l -r", "Output plain list of package names without header"),
            ("{cmd} --install", "Scan and install missing external packages"),
            ("{cmd} -j", "Output dependency mapping as formatted JSON"),
            ("{cmd} -j -r", "Output dependency mapping as compact raw JSON"),
        ],
    )

    args.add_arg("path", required=False, help="Directory to scan (default: script directory)")
    args.add_opt({"-e", "--external"}, help="Show only non-standard library dependencies")
    args.add_opt({"-R", "--recursive"}, help="Scan subdirectories recursively")
    args.add_opt({"-l", "--list"}, help="Show flat list of package names without file mapping")
    args.add_opt({"-r", "--raw"}, "raw_output", help="Output unformatted plain text without ANSI styling or banners")
    args.add_opt({"-j", "--json"}, "as_json", help="Output dependency mapping as formatted JSON")
    args.add_opt({"-i", "--install"}, help="Automatically install all missing external packages")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        (S.ITALIC | S.DIM)("\nCancelled by user.\n").print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

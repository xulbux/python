#!/usr/bin/env python3
# x-tools:file[update]

"""
Lists all installed Visual Studio Code extensions with
the option to directly format them as a JSON list.
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast
import xulbux as xx
from xulbux import ArgumentParser, S

# Make the `_shared` package (cli-tools/_shared) importable when running this script directly:
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared.helpers import print_json

if TYPE_CHECKING:
    from ._shared.helpers import print_json  # ruff:ignore[runtime-import-in-type-checking-block]


def get_common_vscode_locations() -> list[tuple[str, str]]:
    """Returns a list of `(executable_name, path)` tuples for common VS Code locations."""

    locations: list[tuple[str, str]] = []
    system = platform.system()

    if system == "Windows":
        localappdata = os.environ.get("LOCALAPPDATA", "")
        programfiles = os.environ.get("PROGRAMFILES", "")
        programfiles_x86 = os.environ.get("PROGRAMFILES(X86)", "")

        # fmt: off
        if localappdata:
            locations.extend([
                ("code", str(Path(localappdata) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd")),
                ("code-insiders", str(Path(localappdata) / "Programs" / "Microsoft VS Code Insiders" / "bin" / "code-insiders.cmd")),  # ruff:ignore[line-too-long]
            ])
        if programfiles:
            locations.extend([
                ("code", str(Path(programfiles) / "Microsoft VS Code" / "bin" / "code.cmd")),
                ("code-insiders", str(Path(programfiles) / "Microsoft VS Code Insiders" / "bin" / "code-insiders.cmd")),
            ])
        if programfiles_x86:
            locations.extend([
                ("code", str(Path(programfiles_x86) / "Microsoft VS Code" / "bin" / "code.cmd")),
                ("code-insiders", str(Path(programfiles_x86) / "Microsoft VS Code Insiders" / "bin" / "code-insiders.cmd")),
            ])
        # fmt: on

    elif system == "Darwin":
        # fmt: off
        # ruff:ignore[line-too-long]
        locations.extend([
            ("code", "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"),
            ("code-insiders", "/Applications/Visual Studio Code - Insiders.app/Contents/Resources/app/bin/code-insiders"),
            ("code", str(Path.home() / "Applications" / "Visual Studio Code.app" / "Contents" / "Resources" / "app" / "bin" / "code")),
            ("code-insiders", str(Path.home() / "Applications" / "Visual Studio Code - Insiders.app" / "Contents" / "Resources" / "app" / "bin" / "code-insiders")),
            ("code", "/usr/local/bin/code"),
            ("code-insiders", "/usr/local/bin/code-insiders"),
        ])
        # fmt: on

    elif system == "Linux":
        locations.extend([
            ("code", "/usr/bin/code"),
            ("code-insiders", "/usr/bin/code-insiders"),
            ("code", "/usr/local/bin/code"),
            ("code-insiders", "/usr/local/bin/code-insiders"),
            ("code", str(Path.home() / ".local" / "bin" / "code")),
            ("code-insiders", str(Path.home() / ".local" / "bin" / "code-insiders")),
        ])

    return locations


def find_vscode_executable() -> tuple[str, str] | None:
    """Finds VS Code or VS Code Insiders executable.<br>
    Returns a tuple of `(variant_name, executable_path)` or `None` if not found."""

    # First, try to find in `PATH` env variable:
    for variant in ["code", "code-insiders"]:
        try:
            command = "where" if platform.system() == "Windows" else "which"
            result = subprocess.run([command, variant], capture_output=True, check=True, text=True)
            if executable := result.stdout.strip().split("\n")[0]:  # Get first result.
                return (variant, executable)
        except subprocess.CalledProcessError:
            continue

    # If not in `PATH` env-var, check common installation locations:
    for variant, location in get_common_vscode_locations():
        if Path(location).is_file():
            return (variant, location)

    return None


def get_vscode_extensions(executable: str) -> list[str] | None:
    try:
        result = subprocess.run([executable, "--list-extensions"], capture_output=True, text=True, shell=True)
        return result.stdout.strip().splitlines()
    except subprocess.CalledProcessError as exc:
        xx.console.fail(f"Failed to get extensions: {exc.stderr}")


def main() -> None:
    if (vscode_info := find_vscode_executable()) is None:
        S.BR.RED("VS Code is not installed or could not be found.").print()
        raise SystemExit(1)

    variant, executable = vscode_info
    variant_display = "VS Code Insiders" if variant == "code-insiders" else "VS Code"

    extensions = cast("list[str]", get_vscode_extensions(executable))

    if ARGS.as_json.exists:
        print_json(extensions, raw=ARGS.raw_output.exists)
    elif ARGS.raw_output.exists:
        print("\n".join(extensions))
    else:
        title = (S.INVERSE | S.BG.hex("000"))(
            "  Found ", S.BOLD(str(len(extensions))), f" installed {variant_display} extensions  "
        )
        S(
            "",
            "▄" * len(title.raw),
            title,
            "▀" * len(title.raw),
            "",
            "\n".join(extensions),
            "",
            sep="\n",
        ).print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="VS Code Extensions",
        subtitle="List all installed Visual Studio Code extensions",
        examples=[
            ("{cmd}", "List all installed extensions"),
            ("{cmd} -r", "Output plain list of extensions without header"),
            ("{cmd} -j", "Output extensions as formatted JSON"),
            ("{cmd} -j -r", "Output extensions as compact raw JSON"),
        ],
    )

    args.add_opt({"-r", "--raw"}, "raw_output", help="Output unformatted plain text without ANSI colors or banners")
    args.add_opt({"-j", "--json"}, "as_json", help="Output as a JSON list")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

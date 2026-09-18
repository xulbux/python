#!/usr/bin/env python3
# x-tools:file[update]

"""
Execute a command and automatically copy the full output
including metadata to the clipboard, after execution.
"""

import contextlib
import platform
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, cast
import xulbux as xx
from xulbux import ArgumentParser, S

# Make the `_shared` package (cli-tools/_shared) importable when running this script directly:
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared.helpers import format_time

if TYPE_CHECKING:
    from ._shared.helpers import format_time  # ruff:ignore[runtime-import-in-type-checking-block]

try:
    import pyperclip
except Exception as exc:
    S(
        S.RED(S.BOLD("\n[ERROR] "), "'pyperclip' module failed to initialize:"),
        S.BR.RED(f"\n  {'\n  '.join(str(exc).splitlines())}\n"),
    ).print()
    raise SystemExit(1) from exc


def terminate_process(process: subprocess.Popen[str] | None) -> None:
    """Safely terminate a `subprocess.Popen` process."""

    if process is None:
        return

    try:
        process.terminate()
        process.wait(timeout=2)
    except Exception:
        with contextlib.suppress(BaseException):
            process.kill()


def main() -> None:  # ruff:ignore[complex-structure]
    # ********************** PARSE ARGS & INIT **********************

    command_args = ARGS.command.vals()
    exclude_cmd = bool(ARGS.no_command or ARGS.only)
    exclude_meta = bool(ARGS.no_meta or ARGS.only)
    keep_ansi = bool(ARGS.ansi)

    # Properly construct command string for the shell:
    if platform.system() == "Windows":
        # On Windows, use PowerShell-style command with `-command` flag:
        escaped_args: list[str] = []
        for arg in command_args:
            escaped_arg = "'" + arg.replace("'", "''") + "'" if " " in arg or '"' in arg or "'" in arg else arg
            escaped_args.append(escaped_arg)
        command_for_shell = " ".join(escaped_args)
        command_str_display = subprocess.list2cmdline(command_args)
    else:
        command_for_shell = shlex.join(command_args)
        command_str_display = command_for_shell

    S("", S.MAGENTA("━━━ Capturing: ", S.BOLD(command_str_display), " ━━━"), "", sep="\n").print()

    process: subprocess.Popen[str] | None = None
    captured_output: list[str] = []
    add_nl_before_end = True
    start_time = time.time()
    exit_code = 0

    # *********************** RUN THE COMMAND ***********************

    try:
        # `bufsize=1` and `text=True` enables line-by-line text streaming:
        general_popen_kwargs: dict[str, Any] = {
            "bufsize": 1,
            "errors": "replace",  # Replace invalid chars instead of failing.
            "shell": True,  # Use shell to interpret for access to aliases, path, ….
            "stderr": subprocess.STDOUT,  # Merges errors into the main output stream (chronological order).
            "stdin": None,  # Keep STDIN connected to terminal for interactive commands.
            "stdout": subprocess.PIPE,  # Allows us to read it.
            "text": True,
        }

        if platform.system() == "Windows":
            process = subprocess.Popen(
                [
                    "pwsh.exe" if shutil.which("pwsh") else "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [system.Text.Encoding]::UTF8; "
                    + command_for_shell,
                ],
                encoding="utf-8",
                **general_popen_kwargs,
            )
        else:
            process = subprocess.Popen(command_for_shell, encoding=sys.stdout.encoding or "utf-8", **general_popen_kwargs)

        # Stream output to console & capture it:
        while True:
            if not (line := cast("IO[str]", process.stdout).readline()) and process.poll() is not None:
                break
            if line:
                sys.stdout.write(line)
                captured_output.append(line)

        # Wait for process to fully close to get return code:
        exit_code = process.wait()

    except KeyboardInterrupt:
        S(S.BR.YELLOW("\n━━━ Command cancelled by user ━━━", S.DIM(" (Ctrl+C)"))).print()
        add_nl_before_end = False
        exit_code = 130  # `SIGINT`

    except FileNotFoundError:
        error_msg = S(S.RED(S.BOLD("[ERROR] "), "Command not found:"), S.BR.RED(f"  {command_args[0]}"), "\n")
        captured_output.append(error_msg.raw)
        error_msg.print()
        exit_code = 127  # Command not found.

    except Exception as exc:
        error_msg = S(
            S.RED(S.BOLD("\n[ERROR] "), "Command execution failed:"),
            S.BR.RED(f"\n  {'\n  '.join(str(exc).splitlines())}\n"),
        )
        captured_output.append(error_msg.raw)
        error_msg.print()
        exit_code = 1  # General error.

    finally:
        terminate_process(process)

    duration_str = format_time(time.time() - start_time)

    # ******************* BUILD CLIPBOARD CONTENT *******************

    clipboard_parts: list[str] = []

    if not exclude_cmd:
        clipboard_parts.append(
            ("Administrator" if xx.system.is_elevated() else xx.system.get_username())
            + f" on {platform.node()} ({platform.system()})"
            f" at {'~' if (cwd := Path.cwd()).expanduser() == Path.home() else cwd}\n"
            f"$ {command_str_display}\n\n"
        )

    str_output = "".join(captured_output)
    clipboard_parts.append(str_output if keep_ansi else S(str_output).raw)

    if not exclude_meta:
        clipboard_parts.append(
            f"\n{'─' * xx.console.get_width()}\n[{time.ctime(start_time)}]\nTook : {duration_str}\nExit : {exit_code}\n"
        )

    clipboard_content = "".join(clipboard_parts)

    # ****************** COPY TO CLIPBOARD & EXIT *******************

    try:
        pyperclip.copy(clipboard_content)
    except Exception as exc:
        S(
            S.BR.RED(S.BOLD("\n[ERROR] "), "Failed to copy to clipboard:"),
            f"\n  {'\n  '.join(str(exc).splitlines())}\n",
        ).print()
        raise SystemExit(1) from exc

    lines_count = len(captured_output)

    # fmt: off
    S(
        ("\n" if add_nl_before_end else ""),
        (S.BR.GREEN if exit_code == 0 else S.BR.RED)(
            "━━━ Output copied to clipboard ━━━ ",
            S.DIM(
                S.BOLD(str(lines_count)), f" line{'s' if lines_count != 1 else ''} in ",
                S.BOLD(duration_str), ", exit ", S.BOLD(str(exit_code))
            )
        ),
        "\n",
    ).print()
    # fmt: on

    # Exit with the same code as the command:
    raise SystemExit(exit_code)


if __name__ == "__main__":
    args = ArgumentParser(
        title="Execute & Copy",
        subtitle="Run a command and copy its output to clipboard",
        notice=S.BR.YELLOW(
            "⚠ Commands that use dynamic progress bars and such\n",
            "  may not render correctly using this tool.\n",
            S.BOLD("  Interactive STDIN is currently not supported."),
        ),
        usage=(S.BOLD("Usage: "), "{cmd} {opts} {args}"),
        controls=[("Ctrl+C", "Cancel the command and copy the output captured so far")],
        examples=[
            ("{cmd} pip show xulbux", "Run and copy Python lib xulbux info"),
            ("{cmd} --no-meta git status", "Run and copy git status without metadata"),
            ("{cmd} --no-command tree", "Generate and copy a tree listing without the command"),
            ("{cmd} --only ls -la", ("Run and copy ", S.BR.GREEN("ls "), S.BR.BLUE("-la"), " output only")),
        ],
        intermixed=False,
    )

    args.add_arg("command", nargs="+", help="Command to execute with its arguments")
    args.add_opt({"-nc", "--no-command"}, help="Do not include the ran command in clipboard")
    args.add_opt({"-nm", "--no-meta"}, help=("Do not include metadata in clipboard ", S.DIM("(exit code, duration, date)")))
    args.add_opt({"-o", "--only"}, help="Only copy the command output without command or metadata")
    args.add_opt({"-a", "--ansi"}, help=("Keep the ANSI codes in the copied output ", S.DIM("(default: ANSI removed)")))

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

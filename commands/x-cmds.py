#!/usr/bin/env python3
# x-cmds:file[update]

"""
Lists all Python files, executable as commands, in the current directory.
A short description and command arguments are displayed if available.
"""

import hashlib
import re
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, TypedDict, cast
import requests
import xulbux as xx
from xulbux import FormatCodes, LazyRegex, S, StyledText, Throbber
from xulbux.base.types import ArgParseConfigs

"""
[1] WHICH FILES ARE CONSIDERED COMMANDS?
Only files, starting with a python shebang line (e.g., `#!/usr/bin/env python3`), are considered commands.

[2] WHICH FILES WILL BE CHECKED FOR UPDATES?
Only files that include the comment `# x-cmds:file[update]` at the top of the file will be checked for updates from GitHub.

[3] UNLISTED FILES
Files that include the comment `# x-cmds:file[unlisted]` at the top of the file will not appear in the commands list.
Combine options to apply both: `# x-cmds:file[unlisted,update]`
This is useful for shared helper/library files that should be auto-updated but are not standalone commands.

[4] COMMAND DESCRIPTION
The first multi-line comment (triple quotes) at the start of the file is used as a short description.

[5] COMMAND ARGUMENTS & OPTIONS
The use of `get_args()` will automatically be parsed and displayed correctly.
When getting args using `sys.argv`, add a comment to describe the arguments on the line `sys.argv` is used.
The structure of the comment is similar to how the `**arg_parse_configs` kwargs are defined for `get_args()`:
# [pos_arg1: before, arg2: {-a2, --arg2}, arg3: {-a3, --arg3}, pos_arg4: after]
"""


class GithubDiffs(TypedDict):
    """Schema for the differences found between local commands and GitHub."""

    new_commands: list[str]
    updated_commands: list[str]
    deleted_commands: list[str]
    download_urls: dict[str, str]
    fetch_failed: bool


class GithubUpdatesConfig(TypedDict):
    """Schema for GitHub updates configuration."""

    github_repo_urls: list[str]
    check_for_new_commands: bool
    check_for_command_updates: bool


class ScriptConfig(TypedDict):
    """Schema for the script configuration."""

    command_dir: Path
    github_updates: GithubUpdatesConfig


CONFIG: ScriptConfig = {
    "command_dir": xx.fs.get_script_dir(),
    "github_updates": {
        "github_repo_urls": ["https://github.com/xulbux/python/tree/main/commands"],
        "check_for_new_commands": True,
        "check_for_command_updates": True,
    },
}

ARGS = xx.console.get_args({
    "list": {"-l", "--list"},
    "update_check": {"-u", "--update"},
    "help": {"-h", "--help"},
})

PATTERNS = LazyRegex(
    python_shebang=r"(?i)^\s*#!.*python",
    update_marker=r"(?i)^\s*#\s*x-cmds:file\[([\w]+(?:\s*,\s*[\w]+)*)\]\s*$",
    desc=r"(?is)^(?:\s*#!?[^\n]+)*\s*(\"{3}(?:(?!\"\"\").)+\"{3}|'{3}(?:(?!''').)+'{3})",
    sys_argv=r"(?m)(?:#\s*(\[.+?\])\s*)?sys\s*\.\s*argv(?:\[[-:0-9]+\])?(?:\s*#\s*(\[.+?\]))?",
    args_comment=r"(\w+)(?:\s*:\s*(?:\{([^\}]*)\}|(before|after)))?",
    get_args=r"(?m)get_args\s*\(\s*(?:[\w]+\s*=\s*(['\"])[^\1]+\1\s*(?:,\s*)?)?(?:arg_parse_configs\s*=\s*)?\{(?P<brace>(?:[^{}\"']|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\{(?&brace)\})*)\}(?:\s*(?:,\s*)?(?:[\w]+\s*=\s*)?(['\"])[^\3]+\3)?\s*\)",
    arg=r"""\s*(['"])(\w+)\1\s*:\s*(.*)\s*,?""",
)


def print_help() -> None:
    help_text = """
[b|in|bg:black]( CMDs — List and update Python command scripts )

[b](Usage:) [br:green](x-cmds) [br:blue]([options])

[b](Options:)
  [br:blue](-l), [br:blue](--list)      List all commands in a compact one-line format
  [br:blue](-u), [br:blue](--update)    Check GitHub for new/renamed and updated commands

[b](Examples:)
  [br:green](x-cmds)             [dim](# [i](Show all commands with descriptions and arguments))
  [br:green](x-cmds) [br:blue](--list)      [dim](# [i](Show a compact command list))
  [br:green](x-cmds) [br:blue](--update)    [dim](# [i](Check for and apply updates from GitHub))
"""
    FormatCodes.print(help_text)


def is_python_file(filepath: str) -> bool:
    """Check if a file is a Python file by looking for shebang line."""

    try:
        with open(filepath, encoding="utf-8") as file:
            return bool(PATTERNS.python_shebang.match(file.readline()))
    except Exception:
        return False


def get_python_files() -> set[str]:
    """Get all Python files managed by `x-cmds`:<br>
    Commands with a shebang, or any `.py`/`.pyw` file with `x-cmds` markers."""

    python_files: set[str] = set()

    for file_path in CONFIG["command_dir"].iterdir():
        if (
            file_path.is_file()
            and file_path.suffix in {".py", ".pyw"}
            and (is_python_file(str(file_path)) or get_xcmds_options(str(file_path)))
        ):
            python_files.add(file_path.name)

    return python_files


def get_xcmds_options(filepath: str) -> dict[str, bool]:
    """Get options for `x-cmds` set using special `# x-cmds:file[…]` comments."""

    options: dict[str, bool] = {}

    with suppress(Exception), open(filepath, encoding="utf-8") as file:
        for line in file:
            if PATTERNS.python_shebang.match(line):
                continue  # Skip shebang line.
            elif match := PATTERNS.update_marker.match(line):
                for option in (opt.strip().lower() for opt in match.group(1).split(",")):
                    if option == "update":
                        options["update_check"] = True
                    elif option == "unlisted":
                        options["unlisted"] = True
            else:
                break  # Stop at first non-matching line.

    return options


def sort_flags(flags: list[str]) -> list[str]:
    """Sort flags by length (shorter first) and then alphabetically."""

    return sorted(flags, key=lambda x: (len(x) - len(x.lstrip("-")), x))


def arguments_desc(arg_parse_configs: ArgParseConfigs | None) -> str:
    """Generate a formatted description of command arguments
    and options based on the provided configuration."""

    if not arg_parse_configs or len(arg_parse_configs) < 1:
        return "\n\n[b](Takes Options/Arguments) [dim]([[i](unknown)])"

    arg_descs: list[str | list[str]] = []
    keys = list(arg_parse_configs.keys())

    for key, val in arg_parse_configs.items():
        if len(val) < 1:
            arg_descs.append(f"non-flagged argument at position [b]({keys.index(key) + 1})")
        elif isinstance(val, str):
            if val.lower() == "before":
                arg_descs.append("All non-flagged arguments [b](BEFORE) first flag.")
            elif val.lower() == "after":
                arg_descs.append("All non-flagged arguments [b](AFTER) last flag's value.")
            else:
                arg_descs.append(val)
        elif isinstance(val, dict) and "flags" in val:
            arg_descs.append(sort_flags(list(val["flags"])))
        else:
            arg_descs.append(sort_flags(list(val)))

    opt_descs = ["[_c], [br:blue]".join(d) for d in arg_descs if isinstance(d, (list, tuple, set, frozenset))]
    opt_keys = [
        keys.pop(i - j)
        for j, (i, _) in enumerate((i, d) for i, d in enumerate(arg_descs) if isinstance(d, (list, tuple, set, frozenset)))
    ]

    arg_descs = [d for d in arg_descs if isinstance(d, str)]
    arg_keys = [f"<{keys[i]}>" for i, _ in enumerate(arg_descs)]

    left_part_len = max(len(FormatCodes.remove(x)) for x in opt_descs + arg_keys)

    opt_len_diff = [len(d) - len(FormatCodes.remove(d)) for d in opt_descs]
    opt_descs = [
        f"[br:blue]({d:<{left_part_len + opt_len_diff[i]}})    [blue]({FormatCodes.escape(f'[{opt_keys[i]}]')})"
        for i, d in enumerate(opt_descs)
    ]

    arg_descs = [f"[br:cyan]({arg_keys[i]:<{left_part_len}})    [cyan]({d})" for i, d in enumerate(arg_descs)]

    return (
        (
            f"\n\n[b](Takes {len(arg_descs)} Argument{'' if len(arg_descs) == 1 else 's'}:)"
            f"\n  {'\n  '.join(cast('list[str]', arg_descs))}"
        )
        if len(arg_descs) > 0
        else ""
    ) + (
        (f"\n\n[b](Has {len(opt_descs)} Option{'' if len(opt_descs) == 1 else 's'}:)\n  {'\n  '.join(opt_descs)}")
        if len(opt_descs) > 0
        else ""
    )


def parse_args_comment(comment_str: str) -> ArgParseConfigs:
    """Parse an arguments comment string into a structured configuration dictionary."""

    result: ArgParseConfigs = {}

    for match in PATTERNS.args_comment.finditer(cast("re.Match[str]", re.match(r"\[(.*)\]", comment_str)).group(1)):
        key = str(match.group(1))
        if (val := match.group(3)) in {"before", "after"}:
            result[key] = cast("Literal['before', 'after']", val)
        else:
            flags: set[str] = {flag.strip() for flag in match.group(2).split(",")} if match.group(2) else set()
            result[key] = flags

    return result


def parse_file_args(content: str) -> ArgParseConfigs | None:
    """Parse arg configs from file content. Returns None if no args section is detected."""

    sys_argv_matches = cast("list[tuple[str, ...] | str]", PATTERNS.sys_argv.findall(content))
    sys_argv_comments: list[str] = [
        c for groups in sys_argv_matches for c in (groups if isinstance(groups, tuple) else (groups,)) if c
    ]
    get_args_matches = cast("list[tuple[str, ...]]", PATTERNS.get_args.findall(content))
    get_args_funcs = [func_args[1] for func_args in get_args_matches if func_args[1]]

    if not get_args_funcs and not sys_argv_comments:
        return None

    arg_parse_configs: ArgParseConfigs = {}

    with suppress(Exception):
        if get_args_funcs:
            func_args = ""

            if len(get_args_funcs) > 1:
                for fa in get_args_funcs:
                    if fa := fa.strip():
                        func_args = fa
                        break

            else:
                func_args = get_args_funcs[0]
            import ast

            try:
                if isinstance(parsed := ast.literal_eval("{" + func_args + "}"), dict):
                    arg_parse_configs.update(cast("dict[str, Any]", parsed))
            except Exception:
                for arg in PATTERNS.arg.finditer(func_args):
                    if (key := arg.group(2)) and (val := arg.group(3)):
                        arg_parse_configs[key.strip()] = xx.string.to_type(val.strip().rstrip(","))

        else:
            for comment in sys_argv_comments:
                if (comment := comment.strip()).startswith("["):
                    arg_parse_configs.update(parse_args_comment(comment))

    return arg_parse_configs


def get_commands_str(python_files: set[str], list_mode: bool = False) -> str:
    """Generate a formatted string listing all commands, with optional argument hints.<br>
    If `list_mode` is True, a compact one-line format is used."""

    if list_mode:
        cmd_info: list[tuple[str, str]] = []

        for file in sorted(python_files):
            cmd_name = Path(file).stem

            try:
                content = (CONFIG["command_dir"] / file).read_text(encoding="utf-8")
                arg_parse_configs = parse_file_args(content) or {}
            except Exception:
                arg_parse_configs = {}

            before_hints: list[str] = []
            flag_hints: list[str] = []
            help_hints: list[str] = []
            after_hints: list[str] = []

            for key, val in arg_parse_configs.items():
                if isinstance(val, str) and val.lower() == "before":
                    before_hints.append(f"[dim|br:cyan](<{key}>)")
                elif isinstance(val, str) and val.lower() == "after":
                    after_hints.append(f"[dim|br:cyan](<{key}>)")
                elif isinstance(val, dict) and "flags" in val and len(val["flags"]) > 0:
                    flags = sort_flags(list(val["flags"]))
                    hint = f"[dim|br:blue]({flags[0]})"
                    (help_hints if flags[0] in {"-h", "--help"} else flag_hints).append(hint)
                elif isinstance(val, (set, frozenset, list, tuple)) and len(val) > 0:
                    flags = sort_flags(list(val))
                    hint = f"[dim|br:blue]({flags[0]})"
                    (help_hints if flags[0] in {"-h", "--help"} else flag_hints).append(hint)
                else:
                    before_hints.append(f"[dim|br:cyan](<{key}>)")

            hints = before_hints + flag_hints + help_hints + after_hints

            cmd_info.append((cmd_name, f"[_]{' '.join(hints)}" if hints else ""))

        max_len = max((len(name) for name, _ in cmd_info), default=0)
        num_len = len(str(len(cmd_info)))

        return (
            "\n"
            + "\n".join(
                f"[i|dim|br:white]( {i:>{num_len}} )[b|br:white]( {name:<{max_len}}  ){hint}"
                for i, (name, hint) in enumerate(cmd_info, 1)
            )
            + "\n"
        )

    cmds = ""

    for i, file in enumerate(sorted(python_files), 1):
        cmd_name = Path(file).stem
        cmd_title_len = len(str(i)) + len(cmd_name) + 4
        cmds += (
            f"\n[b|br:white|bg:br:white]([[black]{i}[br:white]][in|black]("
            f" {cmd_name} [bg:black]{'━' * (xx.console.get_width() - cmd_title_len)}))"
        )

        with open(CONFIG["command_dir"] / file, encoding="utf-8") as f:
            if desc := PATTERNS.desc.match(content := f.read()):
                cmds += f"\n\n[i]{desc.group(1).strip('\n"\'')}[_]"

        parsed_args = parse_file_args(content)
        if parsed_args is not None:
            cmds += arguments_desc(parsed_args)

        cmds += "\n\n"

    return cmds


def get_github_diffs(local_files: set[str]) -> GithubDiffs:  # ruff:ignore[complex-structure]
    """Check for new files, updated files, and deleted files on GitHub compared to local command-directory."""

    result: GithubDiffs = {
        "new_commands": [],
        "updated_commands": [],
        "deleted_commands": [],
        "download_urls": {},
        "fetch_failed": False,
    }

    with suppress(Exception):
        # Merge files from all GitHub repo URLs:
        github_files: dict[str, dict[str, str]] = {}
        successful_fetches = 0

        for repo_url in CONFIG["github_updates"]["github_repo_urls"]:
            with suppress(Exception):
                # Parse the URL to extract repo info:
                url_pattern = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/(?:tree|blob)/([^/]+)(/.*)?)?", repo_url)
                if not url_pattern:
                    continue

                user, repo, branch, path = url_pattern.groups()
                branch, path = branch or "main", (path or "").strip("/")

                # Use GitHub API to get directory contents:
                api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}"
                if branch:
                    api_url += f"?ref={branch}"

                response = requests.get(api_url, timeout=10)
                response.raise_for_status()

                # Merge files from this repo (later URLs override earlier ones if same name):
                for item in response.json():
                    if item["type"] == "file" and item["name"].endswith((".py", ".pyw")):
                        cmd_name = Path(item["name"]).stem
                        github_files[cmd_name] = {
                            "filename": item["name"],
                            "download_url": item["download_url"],
                            "sha": item["sha"],
                        }

                successful_fetches += 1

        if successful_fetches == 0 and len(CONFIG["github_updates"]["github_repo_urls"]) > 0:
            result["fetch_failed"] = True
            return result  # Bail out to prevent false deletions when GitHub API requests fail.

        # Create mapping from cmd name to actual filename for local files:
        local_file_map = {Path(f).stem: f for f in local_files}
        local_cmd_names = set(local_file_map.keys())

        # Get local files that have update marker:
        local_updateable_files: set[str] = set()
        for filename in local_files:
            filepath = CONFIG["command_dir"] / filename
            options = get_xcmds_options(str(filepath))
            if options.get("update_check"):
                local_updateable_files.add(Path(filename).stem)

        # Check for new files:
        if CONFIG["github_updates"]["check_for_new_commands"]:
            for cmd_name in github_files:
                if cmd_name not in local_cmd_names:
                    result["new_commands"].append(cmd_name)
                    result["download_urls"][github_files[cmd_name]["filename"]] = github_files[cmd_name]["download_url"]

        # Check for updated files (only those with update marker):
        if CONFIG["github_updates"]["check_for_command_updates"]:
            for cmd_name in local_updateable_files:
                if cmd_name in github_files:
                    with suppress(Exception):
                        local_filename = local_file_map[cmd_name]
                        local_path = CONFIG["command_dir"] / local_filename

                        # Read as text and normalize to LF (Unix) line endings like GitHub:
                        with open(local_path, encoding="utf-8", newline="") as f:
                            local_content = f.read().replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")

                        # GitHub uses: "blob " + file size + "\0" + content then SHA1 hash:
                        local_sha = hashlib.sha1(f"blob {len(local_content)}\0".encode() + local_content).hexdigest()

                        # Compare with GitHub's SHA:
                        if local_sha != github_files[cmd_name]["sha"]:
                            result["updated_commands"].append(cmd_name)
                            result["download_urls"][github_files[cmd_name]["filename"]] = github_files[cmd_name][
                                "download_url"
                            ]

        # Check for deleted files (local files with update marker not in GitHub):
        if CONFIG["github_updates"]["check_for_new_commands"]:
            for cmd_name in local_updateable_files:
                if cmd_name not in github_files and cmd_name not in result["updated_commands"]:
                    result["deleted_commands"].append(cmd_name)

    return result


def github_diffs_str(github_diffs: GithubDiffs) -> str:
    """Generate a formatted string summarizing the differences found between local commands and GitHub."""

    if github_diffs.get("fetch_failed", False):
        return (
            "[br:red]✗ Failed to fetch command updates from GitHub.\n"
            "  [dim]Check your internet connection or configuration.[_]\n\n"
        )

    num_new_cmds = len(github_diffs["new_commands"])
    num_cmd_updates = len(github_diffs["updated_commands"])
    num_deleted_cmds = len(github_diffs["deleted_commands"])
    total_changes = num_new_cmds + num_cmd_updates + num_deleted_cmds

    if total_changes == 0:
        return (
            (
                "[magenta](ⓘ [i](You have all available command-files"
                f"{" and they're all up-to-date" if CONFIG['github_updates']['check_for_command_updates'] else ''}.))\n\n"
            )
            if CONFIG["github_updates"]["check_for_new_commands"]
            else "[magenta](ⓘ [i](All your command-files are up-to-date.))\n\n"
        )

    # Build title:
    title_parts: list[str] = []
    if num_new_cmds:
        title_parts.append(f"{num_new_cmds} new command{'' if num_new_cmds == 1 else 's'}")
    if num_cmd_updates:
        title_parts.append(f"{num_cmd_updates} command update{'' if num_cmd_updates == 1 else 's'}")
    if num_deleted_cmds:
        title_parts.append(f"{num_deleted_cmds} command deletion{'' if num_deleted_cmds == 1 else 's'}")

    if len(title_parts) == 1:
        title = f"There {'is' if total_changes == 1 else 'are'} {title_parts[0]} available."
    elif len(title_parts) == 2:
        title = f"There are {title_parts[0]} and {title_parts[1]} available."
    else:
        title = f"There are {title_parts[0]}, {title_parts[1]}, and {title_parts[2]} available."

    diffs_title_len = len(title) + 5
    diffs = (
        f"[b|magenta|bg:magenta]([[black]⇣[magenta]][in|black]( "
        f"{title} [bg:black]{'━' * (xx.console.get_width() - diffs_title_len)}))"
    )

    if num_new_cmds:
        diffs += "\n\n[b](New Commands:)\n  " + "\n  ".join(
            f"[br:green]{cmd}[_]" for cmd in sorted(github_diffs["new_commands"])
        )
    if num_cmd_updates:
        diffs += "\n\n[b](Updated Commands:)\n  " + "\n  ".join(
            f"[br:blue]{cmd}[_]" for cmd in sorted(github_diffs["updated_commands"])
        )
    if num_deleted_cmds:
        diffs += "\n\n[b](Deleted Commands:)\n  " + "\n  ".join(
            f"[br:red]{cmd}[_]" for cmd in sorted(github_diffs["deleted_commands"])
        )

    return diffs


def download_files(github_diffs: GithubDiffs) -> None:
    """Download new and updated files from GitHub, and delete removed files."""

    downloads = github_diffs["download_urls"].items()
    deletions = github_diffs["deleted_commands"]
    total_operations = len(downloads) + len(deletions)

    if total_operations == 0:
        return

    if not xx.console.confirm(StyledText(S.BOLD("\nExecute these updates?")), end="\n", default_is_yes=True):
        FormatCodes.print("[dim|magenta](✗ Not updating commands from GitHub)\n\n")
        return

    success_count = 0

    # Download new and updated files:
    for filename, url in downloads:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Save with or without extension based on platform:
            cmd_name = Path(filename).stem
            file_path = CONFIG["command_dir"] / (filename if xx.system.is_win() else cmd_name)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(response.text)

            # Make executable on Unix-like systems:
            if not xx.system.is_win():
                Path(file_path).chmod(0o755)

            action = "Added" if cmd_name in github_diffs["new_commands"] else "Updated"
            FormatCodes.print(f"[br:green](✓ {action} [b]({cmd_name}))")
            success_count += 1
        except Exception as exc:
            FormatCodes.print(f"[br:red](✗ Failed to download [b]({filename}) [dim]/({exc})[_])")

    # Delete removed files:
    for cmd_name in deletions:
        try:
            # Try both with and without extension:
            deleted = False
            for ext in [".py", ".pyw", ""]:
                file_path = CONFIG["command_dir"] / f"{cmd_name}{ext}"
                if file_path.exists():
                    file_path.unlink()
                    deleted = True
                    break

            if deleted:
                FormatCodes.print(f"[br:green](✓ Deleted [b]({cmd_name}))")
                success_count += 1
            else:
                FormatCodes.print(f"[dim|br:yellow](⚠ Could not find [b]({cmd_name}) to delete)")
        except Exception as exc:
            FormatCodes.print(f"[br:red](✗ Failed to delete [b]({cmd_name}) [dim]/({exc})[_])")

    color = "br:green" if success_count == total_operations else "br:red" if success_count == 0 else "br:yellow"
    FormatCodes.print(
        f"\nSuccessfully completed [{color}]([b]({success_count})/{total_operations})"
        f" operation{'s' if total_operations > 1 else ''}!\n\n"
    )


def main() -> None:

    if ARGS.help.exists:
        print_help()
        return

    python_files = get_python_files()
    listed_files = {file for file in python_files if not get_xcmds_options(str(CONFIG["command_dir"] / file)).get("unlisted")}

    if not ARGS.update_check.exists or ARGS.list.exists:
        FormatCodes.print(get_commands_str(listed_files, list_mode=ARGS.list.exists))
    else:
        print()

    if ARGS.update_check.exists:
        throbber = Throbber(label="⟳ Checking for updates")
        throbber.set_format(["[magenta]({l})", "[b|magenta]({a})"])

        with throbber.context():
            github_diffs = get_github_diffs(python_files)

        FormatCodes.print(github_diffs_str(github_diffs))

        download_files(github_diffs)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

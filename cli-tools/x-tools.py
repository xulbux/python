#!/usr/bin/env python3
# x-tools:file[update]

"""
List and update Python CLI tools in the cli-tools directory.

Provides a compact summary view of all executable Python CLI tools with their arguments
and options, with support for JSON, raw text, and GitHub update synchronization.
"""

import ast
import hashlib
import io
import re
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, TypedDict
import requests
import xulbux as xx
from xulbux import ArgumentParser, S, Term, Throbber

if TYPE_CHECKING:
    from xulbux.ansi import TextRenderable


class ToolArg(NamedTuple):
    """Represents a positional argument of a CLI tool script.\n
    ----------------------------------------------------------------------------------------------------
    *   `name` – Identifier name of the positional argument.
    *   `required` – Whether the positional argument is required.
    *   `nargs` – Arguments value count: integer, '?', '*', or '+'."""

    name: str
    """Identifier name of the positional argument."""
    required: bool
    """Whether the positional argument is required."""
    nargs: int | str = 1
    """Arguments value count: integer, '?', '*', or '+'."""


class ToolOpt(NamedTuple):
    """Represents an option or flag of a CLI tool script.\n
    ----------------------------------------------------------------------------------------------------
    *   `flags` – List of option flags sorted shortest first.
    *   `help` – Optional help text describing the option."""

    flags: list[str]
    """List of option flags sorted shortest first."""
    help: str | None = None
    """Optional help text describing the option."""


class ToolInfo(NamedTuple):
    """Information gathered from a CLI tool script.\n
    ----------------------------------------------------------------------------------------------------
    *   `name` – Stem name of the tool file.
    *   `description` – Short summary description of the tool.
    *   `args` – Positional arguments accepted by the tool.
    *   `options` – Options and flags accepted by the tool."""

    name: str
    """Stem name of the tool file."""
    description: str
    """Short summary description of the tool."""
    args: list[ToolArg]
    """Positional arguments accepted by the tool."""
    options: list[ToolOpt]
    """Options and flags accepted by the tool."""


class GithubDiffs(TypedDict):
    """Schema for the differences found between local tools and GitHub."""

    new_tools: list[str]
    """List of new tool names present only on GitHub."""
    updated_tools: list[str]
    """List of tool names with different file hashes between local and GitHub."""
    deleted_tools: list[str]
    """List of tool names deleted on GitHub but present locally with update marker."""
    download_urls: dict[str, str]
    """Mapping of tool filenames to GitHub raw download URLs."""
    fetch_failed: bool
    """Whether GitHub API requests failed completely."""


class GithubUpdatesConfig(TypedDict):
    """Schema for GitHub updates configuration."""

    github_repo_urls: list[str]
    """List of GitHub repository URLs containing tool files."""
    check_for_new_tools: bool
    """Whether to check for new tools added to GitHub."""
    check_for_tool_updates: bool
    """Whether to check for updates to existing tools."""


class ScriptConfig(TypedDict):
    """Schema for the script configuration."""

    tools_dir: Path
    """Directory containing local CLI tool scripts."""
    github_updates: GithubUpdatesConfig
    """Configuration options for GitHub updates."""


CONFIG: ScriptConfig = {
    "tools_dir": Path(__file__).parent.resolve(),
    "github_updates": {
        "github_repo_urls": ["https://github.com/xulbux/python/tree/main/cli-tools"],
        "check_for_new_tools": True,
        "check_for_tool_updates": True,
    },
}
"""Runtime configuration for tools directory and GitHub repository sync settings."""

SHEBANG_PATTERN: re.Pattern[str] = re.compile(r"(?i)^\s*#!.*python")
"""Pattern matching Python shebang lines at the beginning of script files."""

UPDATE_MARKER_PATTERN: re.Pattern[str] = re.compile(r"(?i)^\s*#\s*(?:x-tools|x-cmds):file\[([\w]+(?:\s*,\s*[\w]+)*)\]\s*$")
"""Pattern matching x-tools file metadata comments (e.g. # x-tools:file[update,unlisted])."""

GITHUB_URL_PATTERN: re.Pattern[str] = re.compile(r"https?://github\.com/([^/]+)/([^/]+)(?:/(?:tree|blob)/([^/]+)(/.*)?)?")
"""Pattern extracting repository owner, name, branch, and sub-path from GitHub URLs."""


class ToolParser(ast.NodeVisitor):
    """AST visitor extracting ArgumentParser definitions, arguments, and options from script content.\n
    ----------------------------------------------------------------------------------------------------
    *   `tree` – Parsed AST tree of the script module."""

    args: list[ToolArg]
    """Positional arguments extracted from ArgumentParser.add_arg calls."""
    options: list[ToolOpt]
    """Options and flags extracted from ArgumentParser.add_opt calls."""
    subtitle: str | None
    """Subtitle extracted from ArgumentParser instantiation if present."""

    def __init__(self) -> None:
        self.args = []
        self.options = []
        self.subtitle = None

    def _parse_argument_parser(self, node: ast.Call) -> None:
        """Extract metadata like subtitle from ArgumentParser constructor calls.\n
        ----------------------------------------------------------------------------------------------------
        *   `node` – AST Call node representing the ArgumentParser instantiation."""

        for keyword in node.keywords:
            if keyword.arg == "subtitle" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                self.subtitle = keyword.value.value

    def _parse_add_arg(self, node: ast.Call) -> None:
        """Extract positional argument definition from an add_arg call.\n
        ----------------------------------------------------------------------------------------------------
        *   `node` – AST Call node representing an add_arg method invocation."""

        if not node.args:
            return

        arg_node = node.args[0]
        if isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str):
            nargs: int | str = 1
            is_required: bool | None = None

            for keyword in node.keywords:
                if keyword.arg == "nargs" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, (int, str)):
                        nargs = keyword.value.value
                elif (
                    keyword.arg == "required"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, bool)
                ):
                    is_required = keyword.value.value

            if is_required is None:
                is_required = nargs not in {"?", "*"}

            self.args.append(ToolArg(name=arg_node.value, required=is_required, nargs=nargs))

    def _parse_add_opt(self, node: ast.Call) -> None:
        """Extract option flags and help description from an add_opt call.\n
        ----------------------------------------------------------------------------------------------------
        *   `node` – AST Call node representing an add_opt method invocation."""

        if not node.args:
            return

        opt_node = node.args[0]
        flags: list[str] = []
        if isinstance(opt_node, (ast.Set, ast.List, ast.Tuple)):
            flags = [
                str(element.value)
                for element in opt_node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
        elif isinstance(opt_node, ast.Constant) and isinstance(opt_node.value, str):
            flags = [opt_node.value]

        if not flags:
            return

        sorted_flags = sorted(flags, key=lambda flag: (len(flag) - len(flag.lstrip("-")), flag))
        help_text: str | None = None
        for keyword in node.keywords:
            if keyword.arg == "help" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                help_text = keyword.value.value

        self.options.append(ToolOpt(flags=sorted_flags, help=help_text))

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "ArgumentParser":
            self._parse_argument_parser(node)

        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_arg":
                self._parse_add_arg(node)
            elif node.func.attr == "add_opt":
                self._parse_add_opt(node)

        self.generic_visit(node)


def inspect_tool_file(filepath: Path) -> ToolInfo:
    """Inspect and extract tool arguments, options, and description from a tool file.\n
    ----------------------------------------------------------------------------------------------------
    *   `filepath` – Path to the CLI tool script file."""

    name = filepath.stem
    content = filepath.read_text(encoding="utf-8")

    try:
        tree = ast.parse(content)
        visitor = ToolParser()
        visitor.visit(tree)

        docstring = ast.get_docstring(tree) or ""
        first_line = docstring.strip().splitlines()[0] if docstring else ""
        description = first_line or visitor.subtitle or ""

        return ToolInfo(
            name=name,
            description=description,
            args=visitor.args,
            options=visitor.options,
        )
    except Exception:
        return ToolInfo(
            name=name,
            description="",
            args=[],
            options=[],
        )


def is_python_file(filepath: Path) -> bool:
    """Check if a file is an executable Python CLI tool by inspecting its shebang line.\n
    ----------------------------------------------------------------------------------------------------
    *   `filepath` – Path to the file to inspect."""

    try:
        with open(filepath, encoding="utf-8") as file:
            return bool(SHEBANG_PATTERN.match(file.readline()))
    except Exception:
        return False


def get_xtools_options(filepath: Path) -> dict[str, bool]:
    """Get options for x-tools configured via special `# x-tools:file[…]` comments.\n
    ----------------------------------------------------------------------------------------------------
    *   `filepath` – Path to the file to inspect."""

    options: dict[str, bool] = {}

    with suppress(Exception), open(filepath, encoding="utf-8") as file:
        for line in file:
            if SHEBANG_PATTERN.match(line):
                continue
            elif match := UPDATE_MARKER_PATTERN.match(line):
                for option in [opt.strip().lower() for opt in match.group(1).split(",")]:
                    if option == "update":
                        options["update_check"] = True
                    elif option == "unlisted":
                        options["unlisted"] = True
            else:
                break

    return options


def get_python_files() -> set[str]:
    """Get all Python CLI tool files managed by x-tools in the tools directory."""

    python_files: set[str] = set()

    for file_path in CONFIG["tools_dir"].iterdir():
        if (
            file_path.is_file()
            and file_path.suffix in {".py", ".pyw"}
            and (is_python_file(file_path) or bool(get_xtools_options(file_path)))
        ):
            python_files.add(file_path.name)

    return python_files


def format_arg_styled(arg: ToolArg) -> S:
    """Format a positional argument into an S styled object matching ArgumentParser help styling.\n
    ----------------------------------------------------------------------------------------------------
    *   `arg` – Positional argument details."""

    l_br, r_br = ("<", ">") if arg.required else ("[", "]")

    match nargs := arg.nargs:
        case "*" | "+":
            return S.BR.CYAN(f"{l_br}{arg.name}...{r_br}")
        case int(n) if n > 1:
            return S.BR.CYAN(f"{l_br}{arg.name} ", S.DIM(f"[{nargs}]"), r_br)
        case _:
            return S.BR.CYAN(f"{l_br}{arg.name}{r_br}")


def format_arg_plain(arg: ToolArg) -> str:
    """Format a positional argument into a plain text string matching ArgumentParser help format.\n
    ----------------------------------------------------------------------------------------------------
    *   `arg` – Positional argument details."""

    l_br, r_br = ("<", ">") if arg.required else ("[", "]")

    match nargs := arg.nargs:
        case "*" | "+":
            return f"{l_br}{arg.name}...{r_br}"
        case int(n) if n > 1:
            return f"{l_br}{arg.name} [{nargs}]{r_br}"
        case _:
            return f"{l_br}{arg.name}{r_br}"


def render_styled_tools(tools: list[ToolInfo]) -> None:
    """Render the tools list as an S styled terminal summary.\n
    ----------------------------------------------------------------------------------------------------
    *   `tools` – List of parsed tool information objects."""

    max_len = max([len(tool.name) for tool in tools], default=0)
    num_len = len(str(len(tools)))

    rows: list[S] = []
    for i, tool in enumerate(tools, 1):
        hints: list[S] = []
        for arg in tool.args:
            hints.append(format_arg_styled(arg))
        for opt in tool.options:
            hints.append(S.BR.BLUE(opt.flags[0]))

        hint_elements: list[S | str] = []
        for hint_index, hint in enumerate(hints):
            if hint_index > 0:
                hint_elements.append(" ")
            hint_elements.append(hint)

        rows.append(
            S(
                (S.ITALIC | S.DIM | S.BR.WHITE)(f" {i:>{num_len}} "),
                (S.BOLD | S.BR.WHITE)(f" {tool.name:<{max_len}}  "),
                *hint_elements,
            )
        )

    S("", *rows, "", sep="\n").print()


def render_raw_tools(tools: list[ToolInfo]) -> None:
    """Render the tools list as plain text without ANSI styling.\n
    ----------------------------------------------------------------------------------------------------
    *   `tools` – List of parsed tool information objects."""

    max_len = max([len(tool.name) for tool in tools], default=0)
    num_len = len(str(len(tools)))

    lines: list[str] = []
    for i, tool in enumerate(tools, 1):
        arg_hints = [format_arg_plain(arg) for arg in tool.args]
        opt_hints = [opt.flags[0] for opt in tool.options]
        hints_str = " ".join(arg_hints + opt_hints)
        lines.append(f" {i:>{num_len}}  {tool.name:<{max_len}}  {hints_str}".rstrip())

    print("\n" + "\n".join(lines) + "\n")


def render_json_tools(tools: list[ToolInfo], *, raw_output: bool) -> None:
    """Render the tools list as formatted or raw JSON.\n
    ----------------------------------------------------------------------------------------------------
    *   `tools` – List of parsed tool information objects.
    *   `raw_output` – Whether to render compact JSON without syntax highlighting."""

    json_data = {
        "total_tools": len(tools),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "args": [{"name": arg.name, "required": arg.required, "nargs": arg.nargs} for arg in tool.args],
                "options": [opt.flags[0] for opt in tool.options],
            }
            for tool in tools
        ],
    }

    xx.data.render(
        json_data,
        indent=2,
        compactness=2 if raw_output else 1,
        as_json=True,
        syntax_highlighting=not raw_output,
    ).print()


def get_github_diffs(local_files: set[str]) -> GithubDiffs:  # ruff:ignore[complex-structure]
    """Check for new files, updated files, and deleted files on GitHub compared to local tools directory.\n
    ----------------------------------------------------------------------------------------------------
    *   `local_files` – Set of local file names to compare against GitHub."""

    result: GithubDiffs = {
        "new_tools": [],
        "updated_tools": [],
        "deleted_tools": [],
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
                if not (url_match := GITHUB_URL_PATTERN.match(repo_url)):
                    continue

                user, repo, branch, path = url_match.groups()
                branch_name = branch or "main"
                path_str = (path or "").strip("/")

                api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{path_str}"
                if branch_name:
                    api_url += f"?ref={branch_name}"

                response = requests.get(api_url, timeout=10)
                response.raise_for_status()

                for item in response.json():
                    if item["type"] == "file" and item["name"].endswith((".py", ".pyw")):
                        tool_name = Path(item["name"]).stem
                        github_files[tool_name] = {
                            "filename": item["name"],
                            "download_url": item["download_url"],
                            "sha": item["sha"],
                        }

                successful_fetches += 1

        if successful_fetches == 0 and len(CONFIG["github_updates"]["github_repo_urls"]) > 0:
            result["fetch_failed"] = True
            return result

        local_file_map = {Path(filename).stem: filename for filename in local_files}
        local_tool_names = set(local_file_map.keys())

        local_updateable_files: set[str] = set()
        for filename in local_files:
            file_path = CONFIG["tools_dir"] / filename
            options = get_xtools_options(file_path)
            if options.get("update_check"):
                local_updateable_files.add(Path(filename).stem)

        if CONFIG["github_updates"]["check_for_new_tools"]:
            for tool_name in github_files:
                if tool_name not in local_tool_names:
                    result["new_tools"].append(tool_name)
                    result["download_urls"][github_files[tool_name]["filename"]] = github_files[tool_name]["download_url"]

        if CONFIG["github_updates"]["check_for_tool_updates"]:
            for tool_name in local_updateable_files:
                if tool_name in github_files:
                    with suppress(Exception):
                        local_filename = local_file_map[tool_name]
                        local_path = CONFIG["tools_dir"] / local_filename

                        with open(local_path, encoding="utf-8", newline="") as file:
                            local_content = file.read().replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")

                        local_sha = hashlib.sha1(f"blob {len(local_content)}\0".encode() + local_content).hexdigest()

                        if local_sha != github_files[tool_name]["sha"]:
                            result["updated_tools"].append(tool_name)
                            result["download_urls"][github_files[tool_name]["filename"]] = github_files[tool_name][
                                "download_url"
                            ]

        if CONFIG["github_updates"]["check_for_new_tools"]:
            for tool_name in local_updateable_files:
                if tool_name not in github_files and tool_name not in result["updated_tools"]:
                    result["deleted_tools"].append(tool_name)

    return result


def github_diffs_str(github_diffs: GithubDiffs) -> S:
    """Generate a formatted S styled object summarizing differences between local tools and GitHub.\n
    ----------------------------------------------------------------------------------------------------
    *   `github_diffs` – Collected difference data from GitHub."""

    if github_diffs.get("fetch_failed", False):
        return S(
            S.BR.RED("✗ Failed to fetch tool updates from GitHub.\n"),
            S.DIM("  Check your internet connection or configuration.\n\n"),
        )

    num_new_tools = len(github_diffs["new_tools"])
    num_tool_updates = len(github_diffs["updated_tools"])
    num_deleted_tools = len(github_diffs["deleted_tools"])
    total_changes = num_new_tools + num_tool_updates + num_deleted_tools

    if total_changes == 0:
        suffix = " and they're all up-to-date." if CONFIG["github_updates"]["check_for_tool_updates"] else "."
        return S.MAGENTA("ⓘ ", S.ITALIC(f"You have all available tools{suffix}\n\n"))

    title_parts: list[str] = []

    if num_new_tools:
        title_parts.append(f"{num_new_tools} new tool{'' if num_new_tools == 1 else 's'}")
    if num_tool_updates:
        title_parts.append(f"{num_tool_updates} tool update{'' if num_tool_updates == 1 else 's'}")
    if num_deleted_tools:
        title_parts.append(f"{num_deleted_tools} tool deletion{'' if num_deleted_tools == 1 else 's'}")

    if len(title_parts) == 1:
        title_text = f"{title_parts[0]} {'is' if total_changes == 1 else 'are'} available."
    elif len(title_parts) == 2:
        title_text = f"{title_parts[0]} and {title_parts[1]} are available."
    else:
        title_text = f"{title_parts[0]}, {title_parts[1]}, and {title_parts[2]} are available."

    title: tuple[TextRenderable, TextRenderable] = (
        (S.BOLD | S.BR.MAGENTA | S.BG.BLACK)("  ⇣  "),
        (S.BOLD | S.hex("000") | S.BG.BR.MAGENTA)(f"  {title_text}  "),
    )
    banner = S(
        "",
        (S.BLACK("▄" * len(title[0].raw)), S.BR.MAGENTA("▄" * len(title[1].raw))),
        (*title,),
        (S.BLACK("▀" * len(title[0].raw)), S.BR.MAGENTA("▀" * len(title[1].raw))),
        sep="\n",
    )

    diff_elements: list[S] = [banner]

    if num_new_tools:
        new_items = [S.BR.GREEN(tool) for tool in sorted(github_diffs["new_tools"])]
        diff_elements.append(S("\n\n", S.BOLD("New Tools:"), "\n  ", S(*new_items, sep="\n  ")))
    if num_tool_updates:
        updated_items = [S.BR.BLUE(tool) for tool in sorted(github_diffs["updated_tools"])]
        diff_elements.append(S("\n\n", S.BOLD("Updated Tools:"), "\n  ", S(*updated_items, sep="\n  ")))
    if num_deleted_tools:
        deleted_items = [S.BR.RED(tool) for tool in sorted(github_diffs["deleted_tools"])]
        diff_elements.append(S("\n\n", S.BOLD("Deleted Tools:"), "\n  ", S(*deleted_items, sep="\n  ")))

    diff_elements.append(S("\n"))
    return S(*diff_elements)


def download_files(github_diffs: GithubDiffs) -> None:
    """Download new and updated files from GitHub, and delete removed files.\n
    ----------------------------------------------------------------------------------------------------
    *   `github_diffs` – Difference details describing downloads and deletions."""

    downloads = list(github_diffs["download_urls"].items())
    deletions = github_diffs["deleted_tools"]
    total_operations = len(downloads) + len(deletions)

    if total_operations == 0:
        return

    if not xx.console.confirm(S.BOLD("\nExecute these updates?"), end="\n", default_is_yes=False):
        (S.DIM | S.MAGENTA)("✗ Not updating tools from GitHub\n\n").print()
        return

    success_count = 0

    for filename, url in downloads:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            tool_name = Path(filename).stem
            file_path = CONFIG["tools_dir"] / (filename if xx.system.is_win() else tool_name)
            file_path.write_text(response.text, encoding="utf-8")

            if not xx.system.is_win():
                file_path.chmod(0o755)

            action = "Added" if tool_name in github_diffs["new_tools"] else "Updated"
            S(S.BR.GREEN(f"✓ {action} "), S.BOLD(tool_name)).print()
            success_count += 1
        except Exception as exc:
            S(S.BR.RED("✗ Failed to download "), S.BOLD(filename), " ", (S.DIM | S.RED)(f"({exc})")).print()

    for tool_name in deletions:
        try:
            deleted = False
            for ext in {".py", ".pyw", ""}:
                file_path = CONFIG["tools_dir"] / f"{tool_name}{ext}"
                if file_path.exists():
                    file_path.unlink()
                    deleted = True
                    break

            if deleted:
                S(S.BR.GREEN("✓ Deleted "), S.BOLD(tool_name)).print()
                success_count += 1
            else:
                (S.DIM | S.BR.YELLOW)("⚠ Could not find ", S.BOLD(tool_name), " to delete").print()
        except Exception as exc:
            S(S.BR.RED("✗ Failed to delete "), S.BOLD(tool_name), " ", (S.DIM | S.RED)(f"({exc})")).print()

    color_style = S.BR.GREEN if success_count == total_operations else S.BR.RED if success_count == 0 else S.BR.YELLOW
    S(
        "\nSuccessfully completed ",
        color_style(S.BOLD(str(success_count)), f"/{total_operations}"),
        f" operation{'s' if total_operations > 1 else ''}!\n\n",
    ).print()


def configure_utf8_output() -> None:
    """Ensure standard output uses UTF-8 encoding across all platforms."""

    with suppress(Exception):
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")  # pyright:ignore[reportUnknownMemberType]


def main() -> None:
    """Execute tool summary or GitHub update check based on parsed CLI arguments."""

    configure_utf8_output()

    python_files = get_python_files()
    listed_files = {file for file in python_files if not get_xtools_options(CONFIG["tools_dir"] / file).get("unlisted")}

    if ARGS.update_check.exists:
        with Throbber(label="Checking for updates...").context():
            github_diffs = get_github_diffs(python_files)

        github_diffs_str(github_diffs).print()
        download_files(github_diffs)
        return

    tools = [inspect_tool_file(CONFIG["tools_dir"] / filename) for filename in sorted(listed_files)]
    raw_output = bool(ARGS.raw_output.exists)

    if ARGS.as_json.exists:
        render_json_tools(tools, raw_output=raw_output)
    elif raw_output:
        render_raw_tools(tools)
    else:
        render_styled_tools(tools)


if __name__ == "__main__":
    configure_utf8_output()

    args = ArgumentParser(
        title="Tools",
        subtitle="List and update Python CLI tools",
        controls=[("Ctrl+C", "Cancel and exit")],
        examples=[
            ("{cmd}", "List all CLI tools in a compact summary format"),
            ("{cmd} -j", "Output tool summary as formatted JSON"),
            ("{cmd} -r", "Output tool summary as plain text"),
            ("{cmd} -j -r", "Output tool summary as unformatted JSON"),
            ("{cmd} -u", "Check for and apply updates from GitHub"),
        ],
    )

    args.add_opt({"-u", "--update"}, "update_check", help="Check GitHub for new/renamed and updated tools")
    args.add_opt({"-j", "--json"}, "as_json", help="Output tool summary as formatted JSON")
    args.add_opt({"-r", "--raw"}, "raw_output", help="Output tool summary as plain text without styling")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        S(Term.CLEAR_LINE, S.RESET, S.BR.RED("✗ Canceled by user.")).print(end="\n\n")
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

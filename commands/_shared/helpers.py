# x-cmds:file[unlisted,update]

"""
Shared helper utilities for commands.
"""

import fnmatch
import os
import re
import stat
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from _shared.consts import HASH_NAME_PATTERN, HEX_SEGMENT_PATTERN, NON_TEXT_EXTS, SEP_SPLITTER_PATTERN, UUID_PATTERN


@lru_cache(maxsize=4096)
def is_likely_hash_name(name: str) -> bool:
    """Determine whether a file or directory name represents an auto-generated hash or identifier.\n
    ----------------------------------------------------------------------------------------------------
    *   `name` – File or directory base name to inspect."""

    if (
        (len(stem := name.rsplit(".", 1)[0] if "." in name else name) < 32 and stem.isalpha())
        or name.strip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_~@. \t{}+/=")
        or len(name) < 2
    ):
        return False
    elif bool(HASH_NAME_PATTERN.match(name)):
        return True

    # Cheap hex-segment check first; UUID regex (more expensive) only as fallback:
    for segment in SEP_SPLITTER_PATTERN.split(stem):
        if len(segment) >= 8 and HEX_SEGMENT_PATTERN.match(segment):
            return True

    return bool(UUID_PATTERN.search(name))


def format_time(elapsed: float) -> str:
    """Format an elapsed time in seconds into a human-readable string.\n
    ----------------------------------------------------------------------------------------------------
    *   `elapsed` – Elapsed time in seconds."""

    m, s = divmod(int(elapsed), 60)
    h, m = divmod(m, 60)
    ms = int((elapsed % 1) * 1000)

    parts: list[str] = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    if s > 0:
        parts.append(f"{s}s")
    if ms > 0:
        parts.append(f"{ms}ms")

    return "".join(parts) if parts else "0ms"


def format_size(size_bytes: int, /) -> str:
    """Format bytes as human-readable size.\n
    ----------------------------------------------------------------------------------------------------
    *   `size_bytes` – Number of bytes to format."""

    size: float = float(size_bytes)

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def is_text_file(filepath: str) -> bool:
    """Determine if a file is a text file by inspecting its extension and bytes.\n
    ----------------------------------------------------------------------------------------------------
    *   `filepath` – Path string to the file to inspect."""

    if Path(filepath).suffix.lower()[1:] in NON_TEXT_EXTS:
        return False

    try:
        with open(filepath, "rb") as file:
            if not (chunk := file.read(1024)):
                return False
            return b"\0" not in chunk

    except Exception:
        return False


def is_hidden_entry(entry: os.DirEntry[str]) -> bool:
    """Check whether a directory entry represents a hidden or system item.\n
    ----------------------------------------------------------------------------------------------------
    *   `entry` – Directory entry to inspect."""

    if entry.name.startswith("."):
        return True

    if os.name == "nt":
        with suppress(AttributeError, OSError):
            file_attrs = entry.stat(follow_symlinks=False).st_file_attributes
            if entry.is_dir(follow_symlinks=False):
                return bool(file_attrs & stat.FILE_ATTRIBUTE_HIDDEN)
            return bool(file_attrs & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))

    else:
        system_dirs = {"/proc", "/sys", "/dev", "/tmp"}
        if (entry_path := entry.path) in system_dirs:
            return True

        for sys_dir in system_dirs:
            if entry_path.startswith(sys_dir):
                return True

    return False


def parse_glob_patterns(raw_input: str) -> list[str]:
    """Parse comma, pipe, or space delimited glob patterns from user input.\n
    ----------------------------------------------------------------------------------------------------
    *   `raw_input` – Raw string containing one or more glob patterns."""

    return [token.strip() for token in raw_input.replace("|", " ").replace(",", " ").split() if token.strip()]


def compile_glob_patterns(patterns: list[str]) -> list[tuple[re.Pattern[str], bool]]:
    """Compile a list of glob patterns into regular expressions.\n
    ----------------------------------------------------------------------------------------------------
    *   `patterns` – List of glob pattern strings."""

    compiled: list[tuple[re.Pattern[str], bool]] = []
    pattern_flags = re.IGNORECASE if os.name == "nt" else 0

    for pattern in patterns:
        if not (clean_pattern := pattern.replace("\\", "/").strip()):
            continue

        target = clean_pattern if (is_name_only := "/" not in clean_pattern) else clean_pattern.lstrip("/")

        with suppress(re.error):
            compiled.append((re.compile(fnmatch.translate(target), pattern_flags), is_name_only))

    return compiled


def matches_glob_patterns(name: str, rel_path: str, patterns: list[tuple[re.Pattern[str], bool]]) -> bool:
    """Check whether a file name or relative path matches any compiled glob pattern.\n
    ----------------------------------------------------------------------------------------------------
    *   `name` – Base name of the file or directory.
    *   `rel_path` – Relative POSIX path from the scanning root directory.
    *   `patterns` – List of compiled pattern regexes with name-only flags."""

    for pattern_regex, is_name_only in patterns:
        if is_name_only:
            if pattern_regex.fullmatch(name) or pattern_regex.fullmatch(rel_path):
                return True
        elif pattern_regex.fullmatch(rel_path):
            return True

    return False


class GitIgnoreRule:
    """Represents a compiled Git ignore rule relative to a root folder.\n
    ----------------------------------------------------------------------------------------------------
    *   `base_dir_posix` – Normalized POSIX string of the folder containing the .gitignore file.
    *   `raw_pattern` – Unparsed line from the .gitignore file."""

    base_dir_posix: str
    """Directory POSIX path string where the .gitignore file is located."""
    negated: bool
    """Whether the pattern is negated with a leading exclamation mark."""
    dir_only: bool
    """Whether the pattern applies exclusively to directories."""
    anchored: bool
    """Whether the pattern is anchored to the base directory."""
    regex: re.Pattern[str]
    """Compiled regular expression for matching paths against the pattern."""

    def __init__(self, base_dir_posix: str, raw_pattern: str) -> None:
        self.base_dir_posix = base_dir_posix.rstrip("/")
        self.negated = (pattern_str := raw_pattern.strip()).startswith("!")

        if self.negated:
            pattern_str = pattern_str[1:].strip()

        self.dir_only = pattern_str.endswith("/")
        self.anchored = "/" in (clean_pattern := pattern_str.rstrip("/")).lstrip("/") or clean_pattern.startswith("/")
        self.regex = re.compile(
            fnmatch.translate(clean_pattern.lstrip("/") if self.anchored else clean_pattern),
            re.IGNORECASE if os.name == "nt" else 0,
        )

    def matches(self, target_full_posix: str, name: str, is_dir: bool) -> bool | None:
        """Check whether this rule matches a target path.\n
        ----------------------------------------------------------------------------------------------------
        *   `target_full_posix` – Full POSIX path of the target item.
        *   `name` – Base name of the target item.
        *   `is_dir` – Whether the path refers to a directory."""

        if (self.dir_only and not is_dir) or not target_full_posix.startswith(self.base_dir_posix):
            return None

        rel = target_full_posix[len(self.base_dir_posix) :].lstrip("/")

        if self.anchored:
            if self.regex.fullmatch(rel):
                return not self.negated

        else:
            if self.regex.fullmatch(name) or self.regex.fullmatch(rel):
                return not self.negated

            for segment in rel.split("/")[:-1]:
                if self.regex.fullmatch(segment):
                    return not self.negated

        return None


def load_gitignore_rules(directory: Path) -> list[GitIgnoreRule]:
    """Load and compile .gitignore rules from a directory and all parent directories.\n
    ----------------------------------------------------------------------------------------------------
    *   `directory` – Directory from which to discover .gitignore files."""

    rules: list[GitIgnoreRule] = []
    hierarchy = [directory, *list(directory.parents)]
    hierarchy.reverse()

    for folder in hierarchy:
        if not (ignore_path := folder / ".gitignore").is_file():
            continue

        folder_posix = str(folder).replace("\\", "/")

        try:
            with open(ignore_path, encoding="utf-8", errors="ignore") as file_handle:
                for line in file_handle:
                    if not (stripped_line := line.strip()) or stripped_line.startswith("#"):
                        continue
                    with suppress(re.error):
                        rules.append(GitIgnoreRule(folder_posix, stripped_line))

        except (OSError, UnicodeDecodeError):
            continue

    return rules


def parse_gitignore_file(gitignore_path: Path) -> list[GitIgnoreRule]:
    """Parse a single .gitignore file and return its compiled rules.\n
    ----------------------------------------------------------------------------------------------------
    *   `gitignore_path` – Path to the .gitignore file."""

    rules: list[GitIgnoreRule] = []
    parent_posix = str(gitignore_path.parent).replace("\\", "/")

    with suppress(OSError, UnicodeDecodeError), open(gitignore_path, encoding="utf-8", errors="ignore") as file_handle:
        for line in file_handle:
            if not (stripped_line := line.strip()) or stripped_line.startswith("#"):
                continue
            with suppress(re.error):
                rules.append(GitIgnoreRule(parent_posix, stripped_line))

    return rules


def is_gitignored(target_full_posix: str, name: str, is_dir: bool, rules: list[GitIgnoreRule]) -> bool:
    """Check whether a path is ignored according to active Git ignore rules.\n
    ----------------------------------------------------------------------------------------------------
    *   `target_full_posix` – Full POSIX path string to inspect.
    *   `name` – Base name of the file or directory.
    *   `is_dir` – Whether the path is a directory.
    *   `rules` – List of active Git ignore rules."""

    if not rules:
        return False

    ignored = False
    for rule in rules:
        if (rule_match := rule.matches(target_full_posix, name, is_dir)) is not None:
            ignored = rule_match

    return ignored


def is_hash_dominated_dir(entries: list[os.DirEntry[str]] | tuple[os.DirEntry[str], ...]) -> bool:
    """Check whether a directory is dominated by generated hash or UUID artifacts.\n
    ----------------------------------------------------------------------------------------------------
    *   `entries` – List of scanned filesystem directory entries."""

    if (total_count := len(entries)) <= 5:
        return False

    hash_count = 0
    for entry in entries:
        if not entry.name.startswith(".") and is_likely_hash_name(entry.name):
            hash_count += 1

    return (hash_count / total_count) > 0.8

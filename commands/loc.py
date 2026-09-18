#!/usr/bin/env python3
# x-cmds:file[update]
"""
Quickly and accurately count lines of code in a directory or project.
"""

import os
import re
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
import xulbux as xx
from xulbux import ArgumentParser, S, Term, Throbber

# Make the `_shared` package (commands/_shared) importable when running this script directly:
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared.consts import EXACT_IGNORE_NAMES, NON_TEXT_EXTS, PATH_IGNORE_PARTS, WILDCARD_IGNORE_NAMES
from _shared.helpers import (
    GitIgnoreRule,
    compile_glob_patterns,
    is_gitignored,
    is_hash_dominated_dir,
    is_hidden_entry,
    is_likely_hash_name,
    load_gitignore_rules,
    matches_glob_patterns,
    parse_gitignore_file,
    parse_glob_patterns,
)

if TYPE_CHECKING:
    from ._shared.consts import EXACT_IGNORE_NAMES, NON_TEXT_EXTS, PATH_IGNORE_PARTS, WILDCARD_IGNORE_NAMES  # ruff:ignore[runtime-import-in-type-checking-block]
    from ._shared.helpers import (  # ruff:ignore[runtime-import-in-type-checking-block]
        GitIgnoreRule,
        compile_glob_patterns,
        is_gitignored,
        is_hash_dominated_dir,
        is_hidden_entry,
        is_likely_hash_name,
        load_gitignore_rules,
        matches_glob_patterns,
        parse_gitignore_file,
        parse_glob_patterns,
    )


# ********************************************************* CONSTANTS *********************************************************

BUFFER_SIZE: int = 65536
"""Buffer size in bytes for reading file chunks during line counting."""
CHECK_LIMIT: int = 8192
"""Maximum number of bytes sampled from a file to determine if it is binary."""


# ****************************************************** HELPER CLASSES *******************************************************


class ScanResult(NamedTuple):
    """Container holding collected line counting statistics.\n
    ----------------------------------------------------------------------------------------------------
    *   `total_lines` – Total number of lines counted across all matched files.
    *   `total_files` – Total count of processed files.
    *   `extensions_data` – Dictionary mapping file extensions to counts of lines and files."""

    total_lines: int
    """Sum of lines of code across all processed files."""
    total_files: int
    """Number of files successfully processed."""
    extensions_data: dict[str, dict[str, int]]
    """Mapping of file extensions to counts of lines and files."""


# ***************************************************** HELPER FUNCTIONS ******************************************************


def should_skip_directory(
    entry: os.DirEntry[str],
    rel_posix: str,
    target_full_posix: str,
    skip_hidden: bool,
    apply_gitignore: bool,
    rules: list[GitIgnoreRule],
    exclude_patterns: list[tuple[re.Pattern[str], bool]],
    include_all: bool,
) -> bool:
    """Check whether a directory entry should be skipped during scanning.\n
    ----------------------------------------------------------------------------------------------------
    *   `entry` – Directory entry to inspect.
    *   `rel_posix` – Relative POSIX path from the scanning root.
    *   `target_full_posix` – Full POSIX path of the directory.
    *   `skip_hidden` – Whether hidden directories should be skipped.
    *   `apply_gitignore` – Whether Git ignore rules are active.
    *   `rules` – List of active Git ignore rules.
    *   `exclude_patterns` – List of compiled exclude glob patterns.
    *   `include_all` – Whether all ignore filters are disabled."""

    name_lower = entry.name.lower()

    if not include_all:
        if name_lower in EXACT_IGNORE_NAMES:
            return True

        if is_likely_hash_name(entry.name):
            return True

        if PATH_IGNORE_PARTS:
            rel_lower = rel_posix.lower()
            for part in PATH_IGNORE_PARTS:
                if part in rel_lower:
                    return True

        for pattern in WILDCARD_IGNORE_NAMES:
            if pattern.fullmatch(name_lower):
                return True

    if entry.name == ".git" and skip_hidden:
        return True

    if skip_hidden and is_hidden_entry(entry):
        return True

    if apply_gitignore and is_gitignored(target_full_posix, entry.name, True, rules):
        return True

    return bool(exclude_patterns and matches_glob_patterns(entry.name, rel_posix, exclude_patterns))


def should_include_file(
    entry: os.DirEntry[str],
    rel_posix: str,
    target_full_posix: str,
    skip_hidden: bool,
    apply_gitignore: bool,
    rules: list[GitIgnoreRule],
    include_patterns: list[tuple[re.Pattern[str], bool]],
    exclude_patterns: list[tuple[re.Pattern[str], bool]],
) -> bool:
    """Check whether a file entry should be processed for line counting.\n
    ----------------------------------------------------------------------------------------------------
    *   `entry` – File entry to inspect.
    *   `rel_posix` – Relative POSIX path from the scanning root.
    *   `target_full_posix` – Full POSIX path of the file.
    *   `skip_hidden` – Whether hidden files should be skipped.
    *   `apply_gitignore` – Whether Git ignore rules are active.
    *   `rules` – List of active Git ignore rules.
    *   `include_patterns` – List of compiled include glob patterns.
    *   `exclude_patterns` – List of compiled exclude glob patterns."""

    if skip_hidden and is_hidden_entry(entry):
        return False

    if apply_gitignore and is_gitignored(target_full_posix, entry.name, False, rules):
        return False

    if exclude_patterns and matches_glob_patterns(entry.name, rel_posix, exclude_patterns):
        return False

    return not (include_patterns and not matches_glob_patterns(entry.name, rel_posix, include_patterns))


def count_lines(file_path: str) -> int:
    """Count lines in a file, returning 0 for empty or binary files.\n
    ----------------------------------------------------------------------------------------------------
    *   `file_path` – Path string of the file to count."""

    try:
        with open(file_path, "rb") as file_handle:
            chunk = file_handle.read(BUFFER_SIZE)
            if not chunk or b"\x00" in chunk[:CHECK_LIMIT]:
                return 0

            line_count = chunk.count(b"\n")
            last_chunk = chunk

            while chunk := file_handle.read(BUFFER_SIZE):
                line_count += chunk.count(b"\n")
                last_chunk = chunk

            if last_chunk and not last_chunk.endswith(b"\n"):
                line_count += 1

            return line_count

    except Exception:
        return 0


# ****************************************************** SCANNING LOGIC *******************************************************


class DirectoryScanner:
    """Orchestrates multi-threaded directory traversal and line counting.\n
    ----------------------------------------------------------------------------------------------------
    *   `target_dir` – Root directory to scan.
    *   `skip_hidden` – Whether hidden and system items should be ignored.
    *   `apply_gitignore` – Whether .gitignore rules should be discovered and enforced.
    *   `include_all` – Whether all ignore filters are disabled.
    *   `is_recursive` – Whether subdirectories should be traversed recursively.
    *   `include_patterns` – Compiled glob patterns to filter included files.
    *   `exclude_patterns` – Compiled glob patterns to filter excluded files/directories."""

    target_dir: Path
    """Root directory where scanning started."""
    skip_hidden: bool
    """Whether to skip hidden and system files/directories."""
    apply_gitignore: bool
    """Whether to load and follow .gitignore rules."""
    include_all: bool
    """Whether all ignore filters are disabled."""
    is_recursive: bool
    """Whether to recurse into subdirectories."""
    include_patterns: list[tuple[re.Pattern[str], bool]]
    """Compiled patterns for inclusion filtering."""
    exclude_patterns: list[tuple[re.Pattern[str], bool]]
    """Compiled patterns for exclusion filtering."""
    total_lines: int
    """Accumulated total code lines count."""
    total_files: int
    """Accumulated total processed files count."""
    extensions_data: dict[str, dict[str, int]]
    """Mapping of file extensions to counts of lines and files."""
    _target_dir_posix: str
    """Normalized POSIX path string of target directory."""
    _lock: threading.Lock
    """Lock synchronizing data mutation across worker threads."""
    _done: threading.Event
    """Event signaling when all queued tasks have completed."""
    _active_tasks: list[int]
    """Single-element list storing active work counter."""
    _canceled: list[bool]
    """Single-element list storing cancellation state."""
    _executor: ThreadPoolExecutor
    """Thread pool executor running scan and count tasks."""

    def __init__(
        self,
        target_dir: Path,
        skip_hidden: bool,
        apply_gitignore: bool,
        include_all: bool,
        is_recursive: bool,
        include_patterns: list[tuple[re.Pattern[str], bool]],
        exclude_patterns: list[tuple[re.Pattern[str], bool]],
    ) -> None:
        self.target_dir = target_dir
        self.skip_hidden = skip_hidden
        self.apply_gitignore = apply_gitignore
        self.include_all = include_all
        self.is_recursive = is_recursive
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns

        self.total_lines = 0
        self.total_files = 0
        self.extensions_data = defaultdict(lambda: {"files": 0, "lines": 0})
        self._target_dir_posix = str(target_dir).replace("\\", "/").rstrip("/")

        self._lock = threading.Lock()
        self._done = threading.Event()
        self._active_tasks = [1]
        self._canceled = [False]
        worker_count = min(64, (os.cpu_count() or 4) * 8)
        self._executor = ThreadPoolExecutor(max_workers=worker_count)

    def _process_entries(
        self,
        dir_path: str,
        entries: list[os.DirEntry[str]],
        active_rules: list[GitIgnoreRule],
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Categorize directory entries into directories to visit and files to count.\n
        ----------------------------------------------------------------------------------------------------
        *   `dir_path` – Directory path currently being processed.
        *   `entries` – List of scanned filesystem directory entries.
        *   `active_rules` – Git ignore rules applicable to this directory level."""

        new_dirs: list[str] = []
        file_tasks: list[tuple[str, str]] = []

        dir_posix = dir_path.replace("\\", "/").rstrip("/")
        if dir_posix == self._target_dir_posix:
            dir_rel = ""
        elif dir_posix.startswith(self._target_dir_posix):
            dir_rel = dir_posix[len(self._target_dir_posix) :].lstrip("/")
        else:
            dir_rel = dir_posix

        for entry in entries:
            name = entry.name
            rel_posix = f"{dir_rel}/{name}" if dir_rel else name
            target_full_posix = f"{dir_posix}/{name}"

            if entry.is_dir(follow_symlinks=False):
                if self.is_recursive and not should_skip_directory(
                    entry,
                    rel_posix,
                    target_full_posix,
                    self.skip_hidden,
                    self.apply_gitignore,
                    active_rules,
                    self.exclude_patterns,
                    self.include_all,
                ):
                    new_dirs.append(entry.path)

            elif entry.is_file(follow_symlinks=False):
                dot = name.rfind(".")
                raw_ext = name[dot + 1 :].lower() if dot >= 0 else ""
                if raw_ext in NON_TEXT_EXTS:
                    continue

                if should_include_file(
                    entry,
                    rel_posix,
                    target_full_posix,
                    self.skip_hidden,
                    self.apply_gitignore,
                    active_rules,
                    self.include_patterns,
                    self.exclude_patterns,
                ):
                    extension = f".{raw_ext}" if raw_ext else "(no ext)"
                    file_tasks.append((entry.path, extension))

        return new_dirs, file_tasks

    def _count_dir_files(self, file_tasks: list[tuple[str, str]]) -> None:
        """Count lines for all files in a directory and merge into global statistics.\n
        ----------------------------------------------------------------------------------------------------
        *   `file_tasks` – List of file path and extension pairs to count."""

        local_lines = 0
        local_files = 0
        local_ext_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])

        for file_path, extension in file_tasks:
            if self._canceled[0]:
                break
            lines = count_lines(file_path)
            local_lines += lines
            local_files += 1
            stats = local_ext_stats[extension]
            stats[0] += 1
            stats[1] += lines

        if local_files > 0 and not self._canceled[0]:
            with self._lock:
                self.total_lines += local_lines
                self.total_files += local_files
                for ext, (f_cnt, l_cnt) in local_ext_stats.items():
                    global_stats = self.extensions_data[ext]
                    global_stats["files"] += f_cnt
                    global_stats["lines"] += l_cnt

    def _finish_task(self) -> None:
        """Decrement the active task counter and signal completion if all work finished."""

        with self._lock:
            self._active_tasks[0] -= 1
            if self._active_tasks[0] == 0:
                self._done.set()

    @staticmethod
    def _resolve_dir_rules(entries: list[os.DirEntry[str]], current_rules: list[GitIgnoreRule]) -> list[GitIgnoreRule]:
        """Discover and append local .gitignore rules if present in directory entries.\n
        ----------------------------------------------------------------------------------------------------
        *   `entries` – List of scanned filesystem directory entries.
        *   `current_rules` – Git ignore rules from parent directories."""

        for entry in entries:
            if entry.name == ".gitignore":
                return [*current_rules, *parse_gitignore_file(Path(entry.path))]

        return current_rules

    def _scan_dir_worker(self, dir_path: str, current_rules: list[GitIgnoreRule]) -> None:
        """Worker task to inspect a directory, dispatch child directories, and count file lines.\n
        ----------------------------------------------------------------------------------------------------
        *   `dir_path` – Directory path to read.
        *   `current_rules` – Git ignore rules applicable to this directory level."""

        if self._canceled[0]:
            self._finish_task()
            return

        try:
            with os.scandir(dir_path) as iterator:
                entries = list(iterator)
        except OSError:
            entries = []

        if not self.include_all and is_hash_dominated_dir(entries):
            self._finish_task()
            return

        active_rules = self._resolve_dir_rules(entries, current_rules) if self.apply_gitignore else current_rules
        new_dirs, file_tasks = self._process_entries(dir_path, entries, active_rules)

        if new_dirs and not self._canceled[0]:
            with self._lock:
                self._active_tasks[0] += len(new_dirs)
            for next_directory in new_dirs:
                self._executor.submit(self._scan_dir_worker, next_directory, active_rules)

        if file_tasks and not self._canceled[0]:
            self._count_dir_files(file_tasks)

        self._finish_task()

    def run(self) -> ScanResult:
        """Start the parallel scanning process and wait until complete."""

        try:
            self._executor.submit(
                self._scan_dir_worker,
                str(self.target_dir),
                load_gitignore_rules(self.target_dir) if self.apply_gitignore else [],
            )

            while not self._done.wait(0.05):
                pass

        except KeyboardInterrupt:
            self._canceled[0] = True
            raise

        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)

        return ScanResult(
            total_lines=self.total_lines,
            total_files=self.total_files,
            extensions_data=dict(self.extensions_data),
        )


def scan_directory(target_dir: Path) -> ScanResult:
    """Scan the target directory recursively and compute line count statistics.\n
    ----------------------------------------------------------------------------------------------------
    *   `target_dir` – Root directory to scan."""

    include_patterns = (
        compile_glob_patterns(parse_glob_patterns(raw_val))
        if ARGS.include_patterns.exists and (raw_val := ARGS.include_patterns.val(default=""))
        else []
    )
    exclude_patterns = (
        compile_glob_patterns(parse_glob_patterns(raw_val))
        if ARGS.exclude_patterns.exists and (raw_val := ARGS.exclude_patterns.val(default=""))
        else []
    )

    include_all = bool(ARGS.include_all.exists)
    scanner = DirectoryScanner(
        target_dir=target_dir,
        skip_hidden=not (ARGS.include_hidden.exists or include_all),
        apply_gitignore=not (ARGS.no_gitignore.exists or include_all),
        include_all=include_all,
        is_recursive=not ARGS.no_recursive.exists,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )

    return scanner.run()


# *********************************************************** MAIN ************************************************************


def main() -> None:
    """Execute the lines of code counter command."""

    target_path = ARGS.target_dir.val(Path, default=Path.cwd())

    if not target_path.exists():
        xx.console.fail(f"Path does not exist: {target_path}", start="\n", end="\n\n", exit_code=1)

    with Throbber(label="Counting lines of code...").context():
        if target_path.is_file():
            file_lines = count_lines(str(target_path))
            scan_result = ScanResult(
                total_lines=file_lines,
                total_files=1,
                extensions_data={target_path.suffix.lower() or "(no ext)": {"files": 1, "lines": file_lines}},
            )
        else:
            scan_result = scan_directory(target_path)

    # [1] Raw numeric output:
    if (raw_output := ARGS.raw_output.exists) and not ARGS.as_json.exists:
        print(scan_result.total_lines)
        return

    # [2] Formatted JSON output:
    if ARGS.as_json.exists:
        xx.data.render(
            {
                "target_dir": str(target_path),
                "total_files": scan_result.total_files,
                "total_lines": scan_result.total_lines,
                "extensions": dict(sorted(scan_result.extensions_data.items())),
            },
            indent=2,
            compactness=2 if raw_output else 1,
            as_json=True,
            syntax_highlighting=not raw_output,
        ).print()
        return

    # [3] Formatted banner output:
    file_count_formatted = f"{scan_result.total_files:,}"
    files_label = f"({file_count_formatted} file)" if scan_result.total_files == 1 else f"({file_count_formatted} files)"

    banner_content = S((S.INVERSE | S.BG.hex("000"))(S.BOLD(f"{scan_result.total_lines:,}"), " total lines  ", files_label))

    S(
        Term.CLEAR_LINE,
        ("▄" * (len(banner_content) + 4)),
        (S.INVERSE("  "), banner_content, S.INVERSE("  ")),
        ("▀" * (len(banner_content) + 4)),
        sep="\n",
    ).print(end="\n\n")

    # [4] Detailed matched extension breakdown:
    sorted_extensions = sorted(
        ((ext_name, ext_data) for ext_name, ext_data in scan_result.extensions_data.items() if ext_data["lines"] > 0),
        key=lambda item: item[1]["lines"],
        reverse=True,
    )

    if sorted_extensions and len(scan_result.extensions_data) > 1:
        max_extension_width = max((len(ext_name) for ext_name, _ in sorted_extensions), default=0)
        max_lines_width = max((len(f"{data['lines']:,}") for _, data in sorted_extensions), default=0)

        extension_rows: list[S] = []
        for extension_name, extension_stats in sorted_extensions:
            lines_str = f"{extension_stats['lines']:,}".rjust(max_lines_width)
            padded_ext = extension_name.ljust(max_extension_width)
            count_label = "file" if extension_stats["files"] == 1 else "files"
            extension_rows.append(
                S(
                    "  ",
                    S.BR.BLUE(padded_ext),
                    "  ",
                    S.BR.WHITE(lines_str),
                    " lines  ",
                    S.DIM(f"({extension_stats['files']:,} {count_label})"),
                )
            )

        S(*extension_rows, sep="\n").print(end="\n\n")


if __name__ == "__main__":
    args = ArgumentParser(
        title="Lines of Code",
        subtitle="Count total lines of code in a directory or project",
        controls=[("Ctrl+C", "Cancel and exit")],
        examples=[
            ("{cmd}", "Count lines of code in the current working directory"),
            ('{cmd} "path/to/my_project"', "Count lines in a specific directory"),
            ('{cmd} -i="*.py | *.toml"', "Count lines only in matching file patterns"),
            ('{cmd} -e="tests/** | build/**"', "Exclude files or directories matching patterns"),
            ("{cmd} -H", "Include hidden and system files/directories"),
            ("{cmd} -a", "Disable all ignore filters; hidden, system, and .gitignore"),
            ("{cmd} -j -r", "Output all gathered statistics as unformatted JSON"),
        ],
    )

    args.add_arg("target_dir", required=False, help=("Target directory to count lines in ", S.DIM("(default: CWD)")))
    args.add_opt(
        {"-i", "--include"},
        "include_patterns",
        expects_value="PATTERNS",
        help=("Include only files matching glob patterns"),
    )
    args.add_opt(
        {"-e", "--exclude"},
        "exclude_patterns",
        expects_value="PATTERNS",
        help=("Exclude files or directories matching glob patterns"),
    )
    args.add_opt({"-ng", "--no-gitignore"}, help="Do not ignore files/directories specified in .gitignore")
    args.add_opt({"-H", "--hidden"}, "include_hidden", help="Do not ignore hidden and system files/directories")
    args.add_opt({"-a", "--all"}, "include_all", help="Disable all ignore filters")
    args.add_opt({"-nr", "--no-recursive"}, help="Do not scan subdirectories recursively")
    args.add_opt({"-j", "--json"}, "as_json", help="Output all gathered statistics as formatted JSON")
    args.add_opt({"-r", "--raw"}, "raw_output", help="Output only the bare total line count number")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        S(Term.CLEAR_LINE, S.RESET, S.BR.RED("✗ Canceled by user.")).print(end="\n\n")
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

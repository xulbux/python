#!/usr/bin/env python3
# x-tools:file[update]

"""
A really advanced directory tree generator
with a lot of options and customization.
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple, TypedDict, cast
import xulbux as xx
from xulbux import ArgumentParser, S, Term, Throbber

# Make the `_shared` package (cli-tools/_shared) importable when running this script directly:
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared.consts import ALL_CATEGORIES, AUTO_IGNORE_FOLDERS, EXT_TO_CAT, Category
from _shared.helpers import format_time, is_likely_hash_name, is_text_file

if TYPE_CHECKING:
    from ._shared.consts import ALL_CATEGORIES, AUTO_IGNORE_FOLDERS, EXT_TO_CAT, Category  # ruff:ignore[runtime-import-in-type-checking-block]
    from ._shared.helpers import format_time, is_likely_hash_name, is_text_file  # ruff:ignore[runtime-import-in-type-checking-block]

    from xulbux.ansi import AnyStyle


COLORS: TreeColorConfig = {
    "line": S.BR.BLACK,
    "line_dull": S.BR.BLACK,
    "error": S.BOLD | S.RED,
    "dir": S.BOLD | S.BR.WHITE,
    "dir_dull": S.BR.WHITE,
    "file": S.WHITE,
    "content": S.DIM | S.WHITE,
    # File type colors:
    "archive": S.BR.RED,
    "audio": S.BR.CYAN,
    "code": S.BR.YELLOW,
    "data": S.YELLOW,
    "doc": S.BR.BLUE,
    "exec": S.BR.GREEN,
    "font": S.BLUE,
    "image": S.BR.MAGENTA,
    "stale": S.DIM | S.BR.WHITE,
    "video": S.MAGENTA,
}

CHARS: TreeCharConfig = {
    "line_ver": "│",
    "line_hor": "─",
    "branch_new": "├",
    "corners": ("╰", "╯", "╮"),
    "error": "⚠",
    "ignored": "…",
    "dirname_end": "/",
}

DEFAULT: ScriptDefaults = {
    "exclude_dirs": [],
    "auto_ignore_mode": 2,
    "truncate_similar": True,
    "include_file_contents": False,
    "max_content_lines": 0,
    "indent_size": 2,
    "into_file": False,
}

TEXT_TRANS = str.maketrans({
    0x2000: " ",
    0x2001: " ",
    0x2002: " ",
    0x2003: " ",
    0x2004: " ",
    0x2005: " ",
    0x2006: " ",
    0x2007: " ",
    0x2008: " ",
    0x2009: " ",
    0x200A: " ",
})


class TreeColorConfig(TypedDict):
    line: AnyStyle
    line_dull: AnyStyle
    error: AnyStyle
    dir: AnyStyle
    dir_dull: AnyStyle
    file: AnyStyle
    content: AnyStyle
    # File type colors:
    archive: AnyStyle
    audio: AnyStyle
    code: AnyStyle
    data: AnyStyle
    doc: AnyStyle
    exec: AnyStyle
    font: AnyStyle
    image: AnyStyle
    stale: AnyStyle
    video: AnyStyle


class TreeCharConfig(TypedDict):
    line_ver: str
    line_hor: str
    branch_new: str
    corners: tuple[str, str, str]
    error: str
    ignored: str
    dirname_end: str


class ScriptDefaults(TypedDict):
    exclude_dirs: list[str]
    auto_ignore_mode: Literal[0, 1, 2]
    truncate_similar: bool
    include_file_contents: bool
    max_content_lines: int
    indent_size: int
    into_file: bool


class DirScanResult(NamedTuple):
    should_ignore: bool
    total_count: int
    hash_count: int
    entries: tuple[os.DirEntry[str], ...]
    sorted_entries: tuple[os.DirEntry[str], ...]


@dataclass
class GenerationStats:
    """Keeps track of statistics during the tree generation process."""

    processed_dirs: int = 0
    processed_files: int = 0
    max_depth: int = 0
    start_time: float = field(default_factory=time.time)


class TreeChars:
    """Manages the visual styling and ANSI codes for the tree."""

    def __init__(self, indent_size: int):
        """Initialize tree styling options and compile required ANSI characters."""

        self.line_ver = CHARS["line_ver"]
        self.line_hor = CHARS["line_hor"]
        self.branch_new = CHARS["branch_new"]
        self.corners = CHARS["corners"]
        self.error = CHARS["error"]
        self.ignored = CHARS["ignored"]
        self.dirname_end = CHARS["dirname_end"]

        self.indent_size = indent_size
        self.indent = " " * (indent_size + 1)
        self.line_hor_str = f"{self.line_hor * max(0, indent_size - 1)} "
        # Pre-computed indent strings used in the hot render path:
        self.indent_cont = f"{self.line_ver}{' ' * indent_size}"
        self.wrap_indent_last = " " * (len(self.corners[0]) + len(self.line_hor_str))
        self.wrap_indent_cont = f"{self.line_ver}{' ' * (len(self.branch_new) + len(self.line_hor_str) - len(self.line_ver))}"

        # Colors as ANSI strings:
        self.c_dim = S.DIM.ansi
        self.c_bold = S.BOLD.ansi
        self.c_bold_in = (S.BOLD | S.INVERSE).ansi
        self.c_italic = S.ITALIC.ansi
        self.c_reset = S.RESET.ansi

        self.c_line = S(self.c_reset, COLORS["line"]).ansi
        self.c_line_dull = S(self.c_reset, COLORS["line_dull"]).ansi
        self.c_error = S(self.c_reset, COLORS["error"]).ansi
        self.c_dir = S(self.c_reset, COLORS["dir"]).ansi
        self.c_dir_dull = S(self.c_reset, COLORS["dir_dull"]).ansi
        self.c_dir_dim = S(self.c_reset, S.DIM, COLORS["dir"]).ansi
        self.c_dir_symlink = S(self.c_reset, COLORS["dir"], S.UNDERLINE).ansi
        self.c_dir_symlink_dim = S(self.c_reset, S.DIM, COLORS["dir"], S.UNDERLINE).ansi
        self.c_file = S(self.c_reset, COLORS["file"]).ansi
        self.c_file_dim = S(self.c_reset, S.DIM, COLORS["file"]).ansi
        self.c_file_symlink = S(self.c_reset, COLORS["file"], S.UNDERLINE).ansi
        self.c_file_symlink_dim = S(self.c_reset, S.DIM, COLORS["file"], S.UNDERLINE).ansi
        self.c_content = S(self.c_reset, COLORS["content"]).ansi

        self.category_colors: dict[Category, tuple[str, str, str, str]] = {
            cat: (
                S(self.c_reset, COLORS[cat]).ansi,
                S(self.c_reset, S.DIM, COLORS[cat]).ansi,
                S(self.c_reset, COLORS[cat], S.UNDERLINE).ansi,
                S(self.c_reset, S.DIM, COLORS[cat], S.UNDERLINE).ansi,
            )
            for cat in ALL_CATEGORIES
        }


class DirectoryScanner:
    """Handles scanning directories and applying ignore rules."""

    def __init__(self, exclude_dirs: list[str], auto_ignore_mode: Literal[0, 1, 2]):
        """Initialize the directory scanner with exclude sets and auto-ignore rules."""

        self.auto_ignore_mode = auto_ignore_mode

        all_folder_ignores = exclude_dirs.copy()
        if auto_ignore_mode > 0:
            all_folder_ignores.extend(path.lower() for path in AUTO_IGNORE_FOLDERS)

        self.exact_names: set[str] = set()
        self.exact_folder_paths: tuple[str, ...] = ()
        self.abs_folder_paths: tuple[tuple[str, str], ...] = ()
        self.wildcard_names: list[re.Pattern[str]] = []
        self.wildcard_paths: list[list[re.Pattern[str]]] = []
        self.wildcard_abs_paths: list[re.Pattern[str]] = []
        self._scan_cache: dict[str, DirScanResult] = {}
        self._ignore_cache: dict[str, bool] = {}

        exact_folder_paths_list: list[str] = []
        abs_folder_paths_list: list[str] = []

        for pattern in all_folder_ignores:
            if Path(pattern := pattern.lower().replace("\\", "/")).is_absolute():
                pattern = f"/{pattern.lstrip('/')}"

            if "*" not in pattern and "[" not in pattern:
                if "/" in pattern:
                    if pattern.startswith("/"):
                        abs_folder_paths_list.append(pattern)
                    else:
                        exact_folder_paths_list.append(pattern)
                else:
                    self.exact_names.add(pattern)

            else:
                if "/" in pattern:
                    if pattern.startswith("/"):
                        self.wildcard_abs_paths.append(re.compile(fnmatch.translate(pattern[1:])))
                    else:
                        parts = [re.compile(fnmatch.translate(part)) for part in pattern.split("/")]
                        self.wildcard_paths.append(parts)
                else:
                    self.wildcard_names.append(re.compile(fnmatch.translate(pattern)))

        self.exact_folder_paths = tuple(exact_folder_paths_list)
        self.abs_folder_paths = tuple((pattern[1:], pattern[1:] + "/") for pattern in abs_folder_paths_list)

    def should_ignore_path(self, path: str) -> bool:  # ruff:ignore[complex-structure]
        """Check if a relative path matches any user-specified or default ignore pattern."""

        if not path:
            return False
        elif (cached := self._ignore_cache.get(path)) is not None:
            return cached

        name = (path_lower := path.lower()).rsplit("/", 1)[-1]

        if name in self.exact_names:
            self._ignore_cache[path] = True
            return True

        if self.abs_folder_paths:
            for exact_rel, prefix_rel in self.abs_folder_paths:
                if path_lower == exact_rel or path_lower.startswith(prefix_rel):
                    self._ignore_cache[path] = True
                    return True

        if self.exact_folder_paths:
            for ep in self.exact_folder_paths:
                if ep in path_lower:
                    self._ignore_cache[path] = True
                    return True

        if self.wildcard_names:
            for w_name in self.wildcard_names:
                if w_name.match(name):
                    self._ignore_cache[path] = True
                    return True

        if self.wildcard_abs_paths:
            for w_name in self.wildcard_abs_paths:
                if w_name.match(path_lower):
                    self._ignore_cache[path] = True
                    return True

        if self.wildcard_paths:
            path_parts = path_lower.split("/")
            for pattern_parts in self.wildcard_paths:
                for i in range(len(path_parts) - (plen := len(pattern_parts)) + 1):
                    if all(pattern_parts[j].match(path_parts[i + j]) for j in range(plen)):
                        self._ignore_cache[path] = True
                        return True

        self._ignore_cache[path] = False
        return False

    def scan_directory(self, dir_path: str) -> DirScanResult:
        """Scan a directory and decide if it should be auto-ignored or partially ignored."""

        if (cached := self._scan_cache.get(dir_path)) is not None:
            return cached

        if self.auto_ignore_mode != 2:
            try:
                with os.scandir(dir_path) as it:
                    raw = tuple(it)
                result = DirScanResult(False, 0, 0, raw, tuple(sorted(raw, key=lambda e: (not e.is_dir(), e.name.lower()))))
            except Exception:
                result = DirScanResult(False, 0, 0, (), ())

            self._scan_cache[dir_path] = result
            return result

        else:
            try:
                with os.scandir(dir_path) as it:
                    entries = tuple(it)
            except Exception:
                entries = ()

            if not entries:
                result = DirScanResult(False, 0, 0, entries, entries)
                self._scan_cache[dir_path] = result
                return result

            # Pre-sort once here (parallel pre-scan phase) so render never needs to sort:
            sorted_entries = tuple(sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower())))

            if (total_count := len(entries)) < 3:
                result = DirScanResult(False, total_count, 0, entries, sorted_entries)
                self._scan_cache[dir_path] = result
                return result

            hash_count = 0

            for entry in entries:
                if (name := entry.name).startswith("."):
                    total_count -= 1
                    continue
                elif is_likely_hash_name(name):
                    hash_count += 1

            sep_pos = max(dir_path.rfind("/"), dir_path.rfind("\\"))
            dir_name = dir_path[sep_pos + 1 :] if sep_pos >= 0 else dir_path

            if total_count > 5 and (hash_count / total_count) > 0.8:
                result = DirScanResult(True, total_count, hash_count, entries, sorted_entries)
            elif is_likely_hash_name(dir_name):
                result = DirScanResult(
                    (total_count > 0 and hash_count / total_count > 0.7), total_count, hash_count, entries, sorted_entries
                )
            else:
                result = DirScanResult(False, total_count, hash_count, entries, sorted_entries)

            self._scan_cache[dir_path] = result
            return result


@dataclass
class TreeConfig:
    base_dir: Path
    max_width: int
    exclude_dirs: list[str] = field(default_factory=lambda: [])
    auto_ignore_mode: Literal[0, 1, 2] = 2
    truncate_similar: bool = True
    include_file_contents: bool = False
    max_content_lines: int = 0
    indent_size: int = 2

    def __post_init__(self):
        """Resolve base directory and set derived properties."""

        self.base_dir = self.base_dir.resolve()


class TreeRenderer:
    """Orchestrates directory traversal and formats the tree output."""

    _RE_DIGIT = re.compile(r"\d+")
    _RE_ALPHA = re.compile(r"[a-zA-Z]")

    def __init__(self, config: TreeConfig):
        """Initialize the renderer with config, styling, and scanner."""

        self.config = config
        self.chrs = TreeChars(config.indent_size)
        self.scanner = DirectoryScanner(config.exclude_dirs, config.auto_ignore_mode)
        self.stats = GenerationStats()
        self._progress_update_interval = 0.05
        self._last_progress_update: float = 0.0
        self._progress_item_count: int = 0
        self._console_width: int = xx.console.get_width()

    def _pre_scan_parallel(self, root_dir: str) -> None:  # ruff:ignore[complex-structure]
        """Pre-populate the scan and ignore caches by scanning all subdirectories in
        parallel before the single-threaded rendering pass. I/O calls release the GIL,
        so a thread pool gives a large real-world speedup on any modern SSD."""

        lock = threading.Lock()
        done = threading.Event()
        active = [1]  # Number of in-flight tasks; pre-counted before each submit.
        canceled = [False]

        def _scan(abs_path: str, rel_path: str) -> None:
            if canceled[0]:
                with lock:
                    active[0] -= 1
                    if active[0] == 0:
                        done.set()
                return

            try:
                if not (result := self.scanner.scan_directory(abs_path)).should_ignore and not canceled[0]:
                    new_items: list[tuple[str, str]] = []

                    # `sorted_entries` has dirs first; break on the first non-dir.
                    for entry in result.sorted_entries:
                        if not entry.is_dir():
                            break
                        elif not self.scanner.should_ignore_path(
                            entry_rel := f"{rel_path}/{entry.name}" if rel_path else entry.name
                        ):
                            new_items.append((entry.path, entry_rel))

                    if new_items and not canceled[0]:
                        with lock:
                            active[0] += len(new_items)
                        for item in new_items:
                            executor.submit(_scan, *item)

            finally:
                with lock:
                    active[0] -= 1
                    if active[0] == 0:
                        done.set()

        executor = ThreadPoolExecutor(max_workers=min(64, (os.cpu_count() or 4) * 8))
        try:
            executor.submit(_scan, root_dir, "")
            while not done.wait(0.1):
                pass
        except KeyboardInterrupt:
            canceled[0] = True
            raise
        finally:
            executor.shutdown(wait=False)

    def generate(self) -> S:
        """Generate the entire directory tree."""

        if not self.config.base_dir.is_dir():
            raise ValueError(f"Invalid base directory: {self.config.base_dir}")

        with Throbber(
            label=S(S.WHITE("Rooting tree from "), S.MAGENTA(str(self.config.base_dir))),
            format=[("  ", S.BR.MAGENTA("{a}")), "{l}"],
        ).context():
            self._pre_scan_parallel(str(self.config.base_dir))

        print()

        lines: list[str] = []
        self._render_tree(str(self.config.base_dir), "", 0, "", lines)
        result_str = "".join(lines)

        print(Term.prev_line() + Term.CLEAR_LINE, end="")  # Clear the last progress output.

        time_taken = S("took ", S.BR.MAGENTA(format_time(time.time() - self.stats.start_time)))
        tree_stats = S(
            ("max depth ", S.BR.MAGENTA(str(self.stats.max_depth))),
            (S.DIM(" | "), S.BR.MAGENTA(f"{self.stats.processed_dirs:,}"), " dirs"),
            (S.DIM(" | "), S.BR.MAGENTA(f"{self.stats.processed_files:,}"), " files"),
        )

        if (space_len := self.config.max_width - len(time_taken.raw) - len(tree_stats.raw) - 2) >= 2:
            footer = (" ", time_taken.ansi, " " * space_len, tree_stats.ansi)
        else:
            footer = (" ", time_taken.ansi, "\n", " " * max(1, self.config.max_width - len(tree_stats.raw)), tree_stats.ansi)

        return S(
            (COLORS["line"], result_str),
            "\n",
            (S.RESET, S.DIM("─" * self.config.max_width), "\n"),
            footer,
            "\n",
        )

    def _update_progress(self, current_name: str, level: int, is_dir: bool = True) -> None:
        """Update the generation progress display in terminal."""

        if is_dir:
            self.stats.processed_dirs += 1
        else:
            self.stats.processed_files += 1

        # Only check wall-clock time every 64 items to avoid sys-call overhead:
        self._progress_item_count += 1
        if self._progress_item_count & 63:
            return  # Fast path: skip ALL remaining work for most calls.

        if level > self.stats.max_depth:
            self.stats.max_depth = level

        if (current_time := time.time()) - self._last_progress_update < self._progress_update_interval:
            return

        self._last_progress_update = current_time

        max_rel_path_len = max(10, self._console_width - 22)
        rel_path = (current_name if len(current_name) <= max_rel_path_len else f".{current_name[-max_rel_path_len:]}") or " "

        xx.console.log(
            "Sprouting",
            f"{self.chrs.c_dir}{rel_path}" if is_dir else f"{self.chrs.c_file}{rel_path}",
            title_bg_color=S.BG.BR.MAGENTA,
            start=Term.prev_line() + Term.CLEAR_LINE,
        )

    def _render_tree(self, dir_path: str, prefix: str, level: int, parent_rel_path: str, lines: list[str]) -> None:
        """Recursively traverse and render the directory tree."""

        sep_pos = max(dir_path.rfind("/"), dir_path.rfind("\\"))
        dir_name = dir_path[sep_pos + 1 :] if sep_pos >= 0 else dir_path
        self._update_progress(dir_name or dir_path, level)

        try:
            if level == 0:
                self._render_root(dir_path, lines)

            if not (entries := (scan_result := self.scanner.scan_directory(dir_path)).sorted_entries):
                return
            elif scan_result.should_ignore:
                self._render_ignored_branch(prefix, is_last=True, lines=lines)
                return

            self._render_entries(entries, prefix, level, parent_rel_path, lines)

        except Exception as exc:
            self._render_error(exc, prefix, lines)

    def _render_root(self, dir_path: str, lines: list[str]) -> None:
        """Render the root directory at the top of the tree."""

        lines.append(
            f"{self.chrs.c_dir}{(path := Path(dir_path)).name or path.drive.rstrip(':\\')}{self.chrs.c_reset}"
            f"{self.chrs.c_dir_dull}{self.chrs.dirname_end}{self.chrs.c_reset}"
            f"{self.chrs.c_line}\n"
        )

    @staticmethod
    def _get_shape(name: str) -> str:
        """Calculate a structural shape signature for a filename."""

        if is_likely_hash_name(name):
            return "[HASH]"

        stem, ext = os.path.splitext(name)
        return f"{TreeRenderer._RE_ALPHA.sub('a', TreeRenderer._RE_DIGIT.sub('#', stem))}{ext.lower()}"

    def _get_visible_entries(self, entries: tuple[os.DirEntry[str], ...]) -> list[os.DirEntry[str] | tuple[int, str]]:
        """Filter entries for inline similarity truncation."""

        if not self.config.truncate_similar or len(entries) < 8:
            return list(entries)

        chunks: list[list[os.DirEntry[str]]] = []
        current_chunk: list[os.DirEntry[str]] = []
        current_shape = ""

        for entry in entries:
            if entry.is_dir():
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_shape = ""
                chunks.append([entry])
                continue

            shape = self._get_shape(entry.name)
            if not current_chunk:
                current_shape = shape
                current_chunk.append(entry)
            elif shape == current_shape:
                current_chunk.append(entry)
            else:
                chunks.append(current_chunk)
                current_chunk = [entry]
                current_shape = shape

        if current_chunk:
            chunks.append(current_chunk)

        visible_entries: list[os.DirEntry[str] | tuple[int, str]] = []

        for chunk in chunks:
            if len(chunk) < 8:
                visible_entries.extend(chunk)
            else:
                visible_entries.extend(chunk[:2])

                # All entries share the same shape => same extension => same color:
                base_color = self._get_file_color(chunk[0])[1]

                visible_entries.append((len(chunk) - 4, base_color))
                visible_entries.extend(chunk[-2:])

        return visible_entries

    def _render_entries(
        self,
        entries: tuple[os.DirEntry[str], ...],
        prefix: str,
        level: int,
        parent_rel_path: str,
        lines: list[str],
    ) -> None:
        """Render directory entries with optional inline similarity truncation."""

        last_idx = len(visible_entries := self._get_visible_entries(entries)) - 1

        for i, item in enumerate(visible_entries):
            branch = self.chrs.corners[0] if (is_last := i == last_idx) else self.chrs.branch_new

            if isinstance(item, tuple):
                count, color = item
                self.stats.processed_files += count

                lines.append(
                    f"{prefix}{branch}{self.chrs.line_hor_str}{color}[{count} more]{self.chrs.c_reset}{self.chrs.c_line}\n"
                )
                continue

            current_prefix = f"{prefix}{branch}{self.chrs.line_hor_str}"

            if item.is_dir():
                current_rel_path = f"{parent_rel_path}/{item.name}" if parent_rel_path else item.name
                if not (should_ignore_entry := self.scanner.should_ignore_path(current_rel_path)):
                    should_ignore_entry = self.scanner.scan_directory(item.path).should_ignore

                if should_ignore_entry:
                    self._render_ignored_entry(item, prefix, is_last, lines)
                    continue

                self._render_directory(item, prefix, current_prefix, level, is_last, current_rel_path, lines)

            else:
                self._render_file(item, prefix, current_prefix, level, is_last, lines)

    def _render_directory(
        self,
        entry: os.DirEntry[str],
        prefix: str,
        current_prefix: str,
        level: int,
        is_last: bool,
        current_rel_path: str,
        lines: list[str],
    ) -> None:
        """Render a single directory node and recursively process its children."""

        if len(entry.name) <= (
            max_name_width := max(10, self.config.max_width - len(current_prefix) - len(self.chrs.dirname_end))
        ):
            lines.append(
                f"{current_prefix}{self.chrs.c_dir}{entry.name}{self.chrs.c_reset}"
                f"{self.chrs.c_dir_dull}{self.chrs.dirname_end}{self.chrs.c_reset}"
                f"{self.chrs.c_line}\n"
            )

        else:
            chunk = textwrap.wrap(entry.name, width=max_name_width, break_long_words=True, drop_whitespace=True)
            lines.append(f"{current_prefix}{self.chrs.c_dir}{chunk[0]}{self.chrs.c_reset}{self.chrs.c_line}\n")

            wrap_prefix = f"{prefix}{self.chrs.wrap_indent_last if is_last else self.chrs.wrap_indent_cont}"

            for part in chunk[1:-1]:
                lines.append(f"{wrap_prefix}{self.chrs.c_dir}{part}{self.chrs.c_reset}{self.chrs.c_line}\n")

            lines.append(
                f"{wrap_prefix}{self.chrs.c_dir}{chunk[-1]}{self.chrs.c_reset}"
                f"{self.chrs.c_dir_dull}{self.chrs.dirname_end}{self.chrs.c_reset}"
                f"{self.chrs.c_line}\n"
            )

        self._render_tree(
            entry.path,
            f"{prefix}{self.chrs.indent if is_last else self.chrs.indent_cont}",
            level + 1,
            current_rel_path,
            lines,
        )

    def _render_file(
        self,
        entry: os.DirEntry[str],
        prefix: str,
        current_prefix: str,
        level: int,
        is_last: bool,
        lines: list[str],
    ) -> None:
        """Render a file node and optionally its contents if configured."""

        self._update_progress(entry.name, level, is_dir=False)
        color, color_dim = self._get_file_color(entry)

        if len(entry.name) <= (max_name_width := max(10, self.config.max_width - len(current_prefix))):
            lines.append(f"{current_prefix}{color}{entry.name}{self.chrs.c_reset}{self.chrs.c_line}\n")

        else:
            chunk = textwrap.wrap(entry.name, width=max_name_width, break_long_words=True, drop_whitespace=True)
            lines.append(f"{current_prefix}{color}{chunk[0]}{self.chrs.c_reset}{self.chrs.c_line}\n")

            wrap_prefix = f"{prefix}{self.chrs.wrap_indent_last if is_last else self.chrs.wrap_indent_cont}"

            for part in chunk[1:]:
                lines.append(f"{wrap_prefix}{color}{part}{self.chrs.c_reset}{self.chrs.c_line}\n")

        if self.config.include_file_contents and is_text_file(entry.path):
            self._render_file_contents(entry.path, prefix, is_last, color_dim, lines)

    def _render_ignored_entry(self, entry: os.DirEntry[str], prefix: str, is_last: bool, lines: list[str]) -> None:
        """Render a specifically ignored node with dimmed styling."""

        if is_last:
            branch = self.chrs.corners[0]
            ignored_prefix = f"{prefix}{self.chrs.indent}"
        else:
            branch = self.chrs.branch_new
            ignored_prefix = f"{prefix}{self.chrs.indent_cont}"

        lines.append(
            f"{prefix}{self.chrs.c_line_dull}{branch}{self.chrs.line_hor_str}{entry.name}{self.chrs.dirname_end}{self.chrs.c_reset}{self.chrs.c_line}\n"
        )

        self._render_ignored_branch(ignored_prefix, is_last=True, lines=lines)

    def _render_ignored_branch(self, prefix: str, is_last: bool, lines: list[str]) -> None:
        """Render a branch indicating collapsed or ignored files."""

        lines.append(
            f"{prefix}{self.chrs.c_line_dull}{self.chrs.corners[0] if is_last else self.chrs.branch_new}"
            f"{self.chrs.line_hor_str}{self.chrs.ignored}{self.chrs.c_reset}{self.chrs.c_line}\n"
        )

    def _render_file_contents(self, filepath: str, prefix: str, is_last: bool, border_color: str, lines: list[str]) -> None:
        """Read and render the contents of a text file into the tree view."""

        indent_str = self.chrs.indent if is_last else self.chrs.indent_cont
        content_prefix = f"{prefix}{indent_str}"

        try:
            with open(filepath, encoding="utf-8", errors="replace") as file:
                file_lines = file.readlines()

            if not file_lines:
                return

            file_lines = [line.replace("\t", "    ").translate(TEXT_TRANS).rstrip() for line in file_lines]
            max_content_width = max(10, self.config.max_width - len(content_prefix) - 4)
            wrapped_lines: list[str] = []

            for line in file_lines:
                if len(line) > max_content_width:
                    chunk = textwrap.wrap(line, width=max_content_width, drop_whitespace=True, break_long_words=True)
                    if not chunk:
                        wrapped_lines.append("")
                    else:
                        wrapped_lines.extend(chunk)
                else:
                    wrapped_lines.append(line)

            file_lines = wrapped_lines
            truncation_msg = ""

            if self.config.max_content_lines > 0 and len(file_lines) > self.config.max_content_lines:
                remaining = len(file_lines) - self.config.max_content_lines
                file_lines = file_lines[: self.config.max_content_lines]
                truncation_msg = f"{remaining} more"

            content_width = max((len(line) for line in file_lines), default=0)

            if truncation_msg:
                content_width = max(content_width, len(truncation_msg))

            hor_border = self.chrs.line_hor * (content_width + 2)

            lines.append(
                f"{self.chrs.c_line}{content_prefix}{border_color}{self.chrs.branch_new}{hor_border}{self.chrs.corners[2]}\n"
            )

            for line in file_lines:
                lines.append(
                    f"{self.chrs.c_line}{content_prefix}{border_color}{self.chrs.line_ver} {line}"
                    f"{self.chrs.c_reset}{border_color}{' ' * (content_width - len(line))} {self.chrs.line_ver}\n"
                )

            if truncation_msg:
                lines.append(
                    f"{self.chrs.c_line}{content_prefix}{border_color}{self.chrs.line_ver} "
                    f"{' ' * (content_width - len(truncation_msg))}{self.chrs.c_italic}{truncation_msg}"
                    f"{self.chrs.c_reset}{border_color} {self.chrs.line_ver}\n"
                )

            lines.append(
                f"{self.chrs.c_line}{content_prefix}{border_color}{self.chrs.corners[0]}{hor_border}{self.chrs.corners[1]}{self.chrs.c_reset}{self.chrs.c_line}\n"
            )

        except Exception:
            lines.append(
                f"{self.chrs.c_line}{content_prefix}{border_color}{self.chrs.corners[0]}{self.chrs.line_hor}"
                f"{self.chrs.c_bold_in}{self.chrs.c_error} {self.chrs.error} "
                f"Error reading file contents. {self.chrs.c_reset}\n{self.chrs.c_line}"
            )

    def _render_error(self, exc: Exception, prefix: str, lines: list[str]) -> None:
        """Render an error message node when a path cannot be accessed."""

        lines.append(
            f"{prefix}{self.chrs.corners[0]}{self.chrs.line_hor_str}{self.chrs.c_bold_in}"
            f"{self.chrs.c_error} {self.chrs.error} {exc!s} {self.chrs.c_reset}\n{self.chrs.c_line}"
        )

    def _get_file_color(self, entry: os.DirEntry[str]) -> tuple[str, str]:
        """Determine the color string for a file based on its type and extension."""

        cat: Category | None = None
        name = entry.name

        if name.endswith("~"):  # Editor backup files.
            cat = "stale"

        else:
            ext = name[dot + 1 :].lower() if (dot := name.rfind(".")) >= 0 else ""

            if name.startswith("."):
                dotfile_ext = name[1:].lower()
                cat = EXT_TO_CAT.get(dotfile_ext)
                if cat is not None:
                    ext = dotfile_ext

            if cat is None:
                cat = EXT_TO_CAT.get(ext)

            if cat is None and not ext:
                with suppress(Exception):
                    if entry.stat(follow_symlinks=False).st_mode & 0o111:
                        cat = "exec"

        if cat is not None:
            colors = self.chrs.category_colors[cat]
            return (colors[2], colors[3]) if entry.is_symlink() else (colors[0], colors[1])

        return (
            (self.chrs.c_file_symlink, self.chrs.c_file_symlink_dim)
            if entry.is_symlink()
            else (self.chrs.c_file, self.chrs.c_file_dim)
        )


def get_user_inputs(config: TreeConfig) -> None:
    """Prompt the user for terminal inputs to construct the TreeConfig interactively."""

    if not ARGS.exclude_dirs.exists:
        exclude_input = xx.console.input(
            (
                S.BOLD("Which directory names/paths should be excluded? "),
                S.DIM("(", S.CYAN("|"), " separated)\n"),
                " > ",
            ),
        )
        config.exclude_dirs = [e_dir.strip() for e_dir in exclude_input.split("|")]

    if not ARGS.auto_ignore_mode.exists:
        config.auto_ignore_mode = cast(
            "Literal[0, 1, 2]",
            xx.console.input(
                (
                    S.BOLD("Auto-ignore unimportant directories?\n"),
                    "0 = None, 1 = Hardcoded only, 2 = Smart\n",
                    (S.DIM(f"({config.auto_ignore_mode})"), " > "),
                ),
                max_len=1,
                allowed_chars="012",
                default_val=config.auto_ignore_mode,
                output_type=int,
            ),
        )

    if not ARGS.truncate_similar.exists:
        config.truncate_similar = (
            xx.console.input(
                (
                    S.BOLD("Truncate repetitive chunks of similarly named files?\n"),
                    (S.DIM("(Y)" if config.truncate_similar else "(N)"), " > "),
                ),
                max_len=1,
                allowed_chars="yYnN",
                default_val="Y" if config.truncate_similar else "N",
            ).upper()
            == "Y"
        )

    if not ARGS.include_file_contents.exists:
        content_input = xx.console.input(
            (
                S.BOLD("How much file contents should be included?\n"),
                "0 = full file contents, N = first N lines\n",
                (S.DIM("(none)"), " > "),
            ),
        )
        if content_input.strip() == "":
            config.include_file_contents = False
        else:
            try:
                config.include_file_contents = True
                config.max_content_lines = max(0, int(content_input))
            except ValueError:
                config.include_file_contents = False

    if not ARGS.indent_size.exists:
        config.indent_size = xx.console.input(
            (
                S.BOLD("What should the indentation size be?\n"),
                (S.DIM(f"({config.indent_size})"), " > "),
            ),
            max_len=2,
            allowed_chars="0123456789",
            default_val=config.indent_size,
            output_type=int,
        )


def main() -> None:  # ruff:ignore[complex-structure]
    print()

    base_dir = Path(opt_val) if (opt_val := ARGS.base_dir.val()) else Path.cwd()

    if ARGS.exclude_dirs.exists:
        exclude_dirs = (
            [e_dir.strip() for e_dir in ARGS.exclude_dirs.val(default="").split("|")] if ARGS.exclude_dirs.values else []
        )
    else:
        exclude_dirs = DEFAULT["exclude_dirs"].copy()

    auto_ignore_mode = DEFAULT["auto_ignore_mode"]

    if ARGS.auto_ignore_mode.exists and (opt_val := ARGS.auto_ignore_mode.val(int)) is not None:
        auto_ignore_mode = cast("Literal[0, 1, 2]", opt_val)

    inc_contents = DEFAULT["include_file_contents"]
    max_lines = DEFAULT["max_content_lines"]

    if (inc_contents := ARGS.include_file_contents.exists) and (opt_val := ARGS.include_file_contents.val(int)) is not None:
        with suppress(ValueError):
            max_lines = max(0, opt_val)

    indent_size = DEFAULT["indent_size"]

    if ARGS.indent_size.exists and (opt_val := ARGS.indent_size.val(int)) is not None:
        with suppress(ValueError):
            indent_size = max(0, opt_val)

    config = TreeConfig(
        base_dir=base_dir,
        max_width=0,  # Set to actual max-width on re-initialization after user input.
        exclude_dirs=exclude_dirs,
        auto_ignore_mode=auto_ignore_mode,
        truncate_similar=not ARGS.truncate_similar.exists,
        include_file_contents=inc_contents,
        max_content_lines=max_lines,
        indent_size=indent_size,
    )

    into_file = DEFAULT["into_file"]
    target_path = Path.cwd() / "tree.txt"

    if (into_file := ARGS.to_file.exists) and (opt_val := ARGS.to_file.val()) is not None:
        if not ((target_path := Path(opt_val).resolve()).is_dir() or target_path.parent.exists()):
            xx.console.fail(("Directory ", S.BR.CYAN(str(target_path.parent)), " does not exist."), end="\n\n", exit_code=1)
        elif target_path.is_dir() or opt_val.endswith("/") or opt_val.endswith("\\"):
            target_path = target_path / "tree.txt"

    if ARGS.interactive.exists:
        get_user_inputs(config)

        if not ARGS.to_file.exists:
            into_file = (
                xx.console.input(
                    (S.BOLD("Output tree to a file?\n"), (S.DIM("(Y)" if into_file else "(N)"), " > ")),
                    max_len=1,
                    allowed_chars="yYnN",
                    default_val="Y" if into_file else "N",
                ).upper()
                == "Y"
            )

        print()

    # Re-initialize config in case user changed properties:
    config = TreeConfig(
        base_dir=config.base_dir,
        max_width=200 if into_file else xx.console.get_width(),
        exclude_dirs=config.exclude_dirs,
        auto_ignore_mode=config.auto_ignore_mode,
        truncate_similar=config.truncate_similar,
        include_file_contents=config.include_file_contents,
        max_content_lines=config.max_content_lines,
        indent_size=config.indent_size,
    )

    renderer = TreeRenderer(config)
    result = renderer.generate()

    if into_file:
        file, cls_line = None, ""
        try:
            file = xx.fs.create_file(target_path, result.raw)
        except FileExistsError:
            cls_line = Term.prev_line() + Term.CLEAR_LINE
            if xx.console.confirm(("  ", S.WHITE(target_path.name), " already exists. Overwrite? "), start=cls_line, end=""):
                file = xx.fs.create_file(target_path, result.raw, force=True)
            else:
                xx.console.exit(start=cls_line, end="\n\n")

        if file:
            xx.console.done(("Generated tree to ", (S.WHITE | S.link(file))(file.name)), start=cls_line, end="\n\n")
        else:
            xx.console.fail((S.BR.RED)("File is empty or failed to create file."), start=cls_line, end="\n\n", exit_code=1)

    else:
        result.print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="Tree Generator",
        subtitle="Quickly generate advanced and good looking directory trees",
        controls=[("Ctrl+C", "Cancel and exit")],
        examples=[
            ("{cmd} -I", "Prompt for interactive settings"),
            ('{cmd} -e="/abs/to/dir1 | rel/to/dir2 | dir3"', "Exclude specified directories"),
            ("{cmd} -i=4", "Set indentation size in spaces"),
            ("{cmd} --auto-ignore=1", "Set auto-ignore mode to hardcoded only"),
            ("{cmd} --no-truncate", "Disable truncation of repetitive chunks"),
            ("{cmd} --content", "Include full file contents"),
            ("{cmd} --content=10", "Include file contents, truncated to 10 lines"),
            ('{cmd} -f="/path/to/dir_or_file"', "Output to specific file or directory"),
        ],
        epilog=S(
            (
                S.BOLD("Prompts: "),
                S.DIM("(only when using the ", S.BR.BLUE("-I"), " or ", S.BR.BLUE("--interactive"), " option)"),
            ),
            ("  ", (S.ITALIC | S.DIM)("1"), "  Directories to exclude"),
            ("  ", (S.ITALIC | S.DIM)("2"), "  Auto-ignore mode"),
            ("  ", (S.ITALIC | S.DIM)("3"), "  Truncate repetitive chunks of similarly named files"),
            ("  ", (S.ITALIC | S.DIM)("4"), "  Include file contents"),
            ("  ", (S.ITALIC | S.DIM)("5"), "  Indentation size"),
            ("  ", (S.ITALIC | S.DIM)("6"), "  Output tree to file"),
            sep="\n",
        ),
    )

    args.add_arg("base_dir", required=False, help=("Base directory to generate tree from ", S.DIM("(default: CWD)")))
    args.add_opt(
        {"-e", "--exclude"},
        "exclude_dirs",
        expects_value="S",
        help=("Directories to exclude ", S.DIM("(directory paths/names, separated by ", S.BR.CYAN("|"), ")")),
    )
    args.add_opt(
        {"-a", "--auto-ignore"},
        "auto_ignore_mode",
        expects_value="N",
        choices=("0", "1", "2"),
        help=("Auto-ignore mode (0: OFF, 1: Hardcoded only, 2: Smart) ", S.DIM(f"(default: {DEFAULT['auto_ignore_mode']})")),
    )
    args.add_opt({"-nt", "--no-truncate"}, "truncate_similar", help="Disable truncation of repetitive similar-filename chunks")
    args.add_opt(
        {"-c", "--content"},
        "include_file_contents",
        expects_value="N",
        help=("Include file contents, optionally truncated to ", S.BR.BLUE("N"), " lines"),
    )
    args.add_opt(
        {"-i", "--indent"},
        "indent_size",
        expects_value="N",
        help=("Used indentation size for tree display ", S.DIM(f"(default: {DEFAULT['indent_size']})")),
    )
    args.add_opt(
        {"-f", "--file"},
        "to_file",
        expects_value="PATH?",
        help=(
            "Output tree into file ",
            S.DIM("(default: ", S.WHITE("tree.txt"), " in ", S.WHITE("CWD"), " if ", S.BR.BLUE("PATH"), " is omitted)"),
        ),
    )
    args.add_opt({"-I", "--interactive"}, help="Prompt for interactive tree settings")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        S(S.RESET, Term.prev_line(), Term.CLEAR_LINE, S.BR.RED("✗ Canceled by user.")).print(end="\n\n")
    except PermissionError:
        xx.console.fail("Permission to create file was denied.", start="\n", end="\n\n", exit_code=1)
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

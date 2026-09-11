#!/usr/bin/env python3
# ruff:file-ignore[ambiguous-unicode-character-string]
# x-cmds:file[update]

"""
Play a maze game in the console.
Controls and options are shown on startup.
"""

import array
import math
import random
import sys
import time
from collections import deque
from heapq import heappop, heappush
from pathlib import Path
from typing import Final, TypedDict
import xulbux as xx
from xulbux import ArgumentParser, S, Throbber
from xulbux.base.consts import KEYS

DIRECTIONS: Final[dict[str, tuple[int, int]]] = {
    **dict.fromkeys(KEYS.UP, (-1, 0)),
    **dict.fromkeys(KEYS.DOWN, (1, 0)),
    **dict.fromkeys(KEYS.LEFT, (0, -1)),
    **dict.fromkeys(KEYS.RIGHT, (0, 1)),
    "a": (0, -1),
    "d": (0, 1),
    "s": (1, 0),
    "w": (-1, 0),
}
"""Mapping of movement keys, escape sequences, and scan codes to coordinate offsets (dy, dx)."""
ENTER_KEYS: Final[frozenset[str]] = KEYS.ENTER
"""Key representations that trigger normal mode execution."""
CTRL_ENTER_KEYS: Final[frozenset[str]] = KEYS.CTRL_ENTER | {"a"}
"""Key representations that trigger ASCII mode execution (Ctrl+Enter or A)."""


class RenderOpts(TypedDict):
    """Render options for the maze game."""

    bg: str
    """Character or string used to represent empty background cells."""
    wall: str
    """Character or string used to represent maze walls."""
    start: str
    """Character or string used to represent the starting position."""
    goal: str
    """Character or string used to represent the goal position."""
    player: str
    """Character or string used to represent the player."""
    solution: str
    """Character or string used to represent solution path tiles."""
    stretch_w: int
    """Horizontal stretch multiplier applied to rendered tile characters."""


class Maze:
    """Generate and play an interactive maze in the terminal or export it to text files.\n
    ----------------------------------------------------------------------------------------------------
    *   `width` – Total character width of the maze, including outer borders.
    *   `height` – Total character height of the maze, including outer borders.
    *   `bg` – Byte character representation for traversable background passages.
    *   `wall` – Byte character representation for solid maze walls.
    *   `start` – Byte character representation for the starting point tile.
    *   `goal` – Byte character representation for the goal destination tile.
    *   `player` – Byte character representation for the player avatar tile.
    *   `solution` – Byte character representation for the solved path tiles.
    *   `render_opts` – Custom visual tile mapping and styling options dictionary.
    *   `render_ascii` – Whether to render using simple monochrome ASCII characters
        instead of ANSI colors."""

    def __init__(
        self,
        width: int,
        height: int,
        /,
        *,
        bg: str = "0",
        wall: str = "1",
        start: str = "2",
        goal: str = "3",
        player: str = "4",
        solution: str = "5",
        render_opts: RenderOpts | None = None,
        render_ascii: bool = False,
    ) -> None:
        # Pre-compute tiles:
        self.bg_byte: int = ord(bg)
        self.wall_byte: int = ord(wall)
        self.start_byte: int = ord(start)
        self.goal_byte: int = ord(goal)
        self.player_byte: int = ord(player)
        self.solution_byte: int = ord(solution)

        # Render:
        self.render_opts: RenderOpts = (
            {
                "bg": " ",
                "wall": "░",
                "start": " ",
                "goal": "▞",
                "player": "█",
                "solution": "▒",
                "stretch_w": 2,
            }
            if render_ascii
            else {
                "bg": " ",
                "wall": "░",
                "start": S.RED("█").ansi,
                "goal": S.GREEN("█").ansi,
                "player": S.BLUE("█").ansi,
                "solution": (S.DIM | S.BR.BLUE)("▒").ansi,
                "stretch_w": 2,
            }
        )

        if render_opts is not None:
            self.render_opts.update(render_opts)

        self.show_solution: bool = False
        self.render_ascii: bool = render_ascii
        self.render_opts["stretch_w"] = max(1, self.render_opts["stretch_w"])

        self.rendered_tiles: dict[int, str] = {
            self.bg_byte: self._render_char(self.render_opts["bg"]),
            self.wall_byte: self._render_char(self.render_opts["wall"]),
            self.start_byte: self._render_char(self.render_opts["start"]),
            self.goal_byte: self._render_char(self.render_opts["goal"]),
            self.player_byte: self._render_char(self.render_opts["player"]),
            self.solution_byte: self._render_char(self.render_opts["solution"]),
        }

        # Generate maze:
        self.width: int = width - 2
        self.height: int = height - 2
        self.maze = self._generate()

        # Positions:
        self.start_pos: tuple[int, int] = self._get_pos(self.start_byte) or (0, 0)
        self.goal_pos: tuple[int, int] = self._get_pos(self.goal_byte) or (0, 0)
        self.player_pos: list[int] = list(self.start_pos)

        # Player:
        self.under_player: int = self.maze[self.player_pos[0]][self.player_pos[1]]
        self._move_player(0, 0)

    def play(self) -> None:
        """Hide the cursor and start the interactive game loop until completed or interrupted."""

        self.goal_reached: bool = False
        sys.stdout.write("\x1b[?25l")
        sys.stdout.flush()
        try:
            self._game_main_loop()
        finally:
            sys.stdout.write("\x1b[?25h")
            sys.stdout.flush()

    def _find_start_pos(self, maze: list[bytearray], /, *, center_y: int, center_x: int) -> tuple[int, int]:
        """Find the traversable floor position furthest from the center via breadth-first search.\n
        ----------------------------------------------------------------------------------------------------
        *   `maze` – Two-dimensional byte grid of the maze layout.
        *   `center_y` – Vertical row index of the starting center point.
        *   `center_x` – Horizontal column index of the starting center point."""

        visited: set[tuple[int, int]] = set()
        queue = deque([(center_y, center_x, 0)])
        furthest_point = (center_y, center_x)
        max_dist = 0
        height, width = len(maze), len(maze[0])

        while queue:
            y, x, dist = queue.popleft()

            if dist > max_dist and maze[y][x] == self.bg_byte:
                max_dist = dist
                furthest_point = (y, x)

            for dy, dx in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                new_y, new_x = y + dy, x + dx
                pos = (new_y, new_x)

                if pos not in visited and 0 <= new_y < height and 0 <= new_x < width and maze[new_y][new_x] == self.bg_byte:
                    visited.add(pos)
                    queue.append((new_y, new_x, dist + 1))

        return furthest_point

    def _trim_borders(self, maze: list[bytearray], /) -> list[bytearray]:
        """Strip redundant outer wall rows and columns until the maze boundary is reached.\n
        ----------------------------------------------------------------------------------------------------
        *   `maze` – Two-dimensional byte grid of the maze layout to trim."""

        while maze and maze[0]:
            if {row[0] for row in maze} == {self.wall_byte}:
                maze = [row[1:] for row in maze]
            elif {row[-1] for row in maze} == {self.wall_byte}:
                maze = [row[:-1] for row in maze]
            elif set(maze[0]) == {self.wall_byte}:
                maze = maze[1:]
            elif set(maze[-1]) == {self.wall_byte}:
                maze = maze[:-1]
            else:
                break
        return maze

    def _add_borders(self, maze: list[bytearray], /) -> list[bytearray]:
        """Enclose the two-dimensional maze layout within a solid outer wall border.\n
        ----------------------------------------------------------------------------------------------------
        *   `maze` – Two-dimensional byte grid of the maze layout to enclose."""

        border = bytearray([self.wall_byte] * (len(maze[0]) + 2))
        return [border] + [bytearray([self.wall_byte]) + row + bytearray([self.wall_byte]) for row in maze] + [border]

    def _generate(self) -> list[bytearray]:
        """Generate a randomized maze grid using iterative depth-first search and trim excess borders."""

        width = self.width if self.width % 2 == 1 else self.width - 1
        height = self.height if self.height % 2 == 1 else self.height - 1
        center_y, center_x = height // 2, width // 2
        maze = array.array("B", [self.wall_byte] * (width * height))

        def idx(x: int, y: int) -> int:
            """Calculate the one-dimensional buffer index for given (x, y) coordinates.\n
            ----------------------------------------------------------------------------------------------------
            *   `x` – Horizontal grid coordinate.
            *   `y` – Vertical grid coordinate."""

            return y * width + x

        stack = [(center_x, center_y)]
        maze[idx(center_x, center_y)] = self.bg_byte

        while stack:
            x, y = stack[-1]
            directions = [(0, 2), (2, 0), (0, -2), (-2, 0)]
            random.shuffle(directions)
            found_path = False

            for dx, dy in directions:
                new_x, new_y = x + dx, y + dy

                if 0 <= new_x < width and 0 <= new_y < height and maze[idx(new_x, new_y)] == self.wall_byte:
                    maze[idx(x + dx // 2, y + dy // 2)] = self.bg_byte
                    maze[idx(new_x, new_y)] = self.bg_byte
                    stack.append((new_x, new_y))
                    found_path = True
                    break

            if not found_path:
                stack.pop()

        maze_2d: list[bytearray] = []

        for y in range(height):
            start_idx = y * width
            row = bytearray(maze[start_idx : start_idx + width])
            maze_2d.append(row)

        start_pos = self._find_start_pos(maze_2d, center_y=center_y, center_x=center_x)
        maze_2d[center_y][center_x] = self.goal_byte
        maze_2d[start_pos[0]][start_pos[1]] = self.start_byte
        final_maze = self._trim_borders(maze_2d)

        return self._add_borders(final_maze)

    def _render_char(self, char: str, /) -> str:
        """Repeat a character horizontally according to the configured stretch width.\n
        ----------------------------------------------------------------------------------------------------
        *   `char` – Single character or ANSI escape sequence string to stretch."""

        return char * self.render_opts["stretch_w"]

    def _get_pos(self, tile: int, /) -> tuple[int, int] | None:
        """Find the (y, x) row and column indices of the first matching tile byte in the maze.\n
        ----------------------------------------------------------------------------------------------------
        *   `tile` – Byte value representing the target tile to locate."""

        for y, row in enumerate(self.maze):
            try:
                return (y, row.index(tile))
            except ValueError:
                continue

        return None

    def _move_player(self, dy: int, dx: int, /) -> None:
        """Update the player position by delta offsets if the destination cell is not a wall.\n
        ----------------------------------------------------------------------------------------------------
        *   `dy` – Vertical row movement delta (-1 for up, 1 for down).
        *   `dx` – Horizontal column movement delta (-1 for left, 1 for right)."""

        new_y = self.player_pos[0] + dy
        new_x = self.player_pos[1] + dx
        if self.maze[new_y][new_x] == self.wall_byte:
            return
        self.maze[self.player_pos[0]][self.player_pos[1]] = self.under_player
        self.player_pos[0], self.player_pos[1] = new_y, new_x
        self.under_player = self.maze[new_y][new_x]
        self.maze[new_y][new_x] = self.player_byte

    def _reconstruct_path(
        self,
        came_from: dict[tuple[int, int], tuple[int, int]],
        current: tuple[int, int],
        start: tuple[int, int],
        /,
    ) -> set[tuple[int, int]]:
        """Reconstruct the path coordinates from A* came_from predecessor links.\n
        ----------------------------------------------------------------------------------------------------
        *   `came_from` – Mapping of node positions to their immediate predecessor.
        *   `current` – Terminal goal node position.
        *   `start` – Origin starting node position."""

        path: list[tuple[int, int]] = []
        while current in came_from:
            path.append(current)
            current = came_from[current]
        path.append(start)
        return set(path)

    def _find_path(self, start: int = ord("2"), goal: int = ord("3"), /) -> set[tuple[int, int]]:
        """Compute the shortest path between start and goal tiles using the A* search algorithm.\n
        ----------------------------------------------------------------------------------------------------
        *   `start` – Byte value representing the starting position tile.
        *   `goal` – Byte value representing the destination goal tile."""

        if (start_pos := self._get_pos(start)) is None or (goal_pos := self._get_pos(goal)) is None:
            return set()

        height, width = len(self.maze), len(self.maze[0])
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        target_pos = goal_pos

        def manhattan_distance(pos1: tuple[int, int], /) -> int:
            """Calculate the Manhattan distance from a position to the destination goal.\n
            ----------------------------------------------------------------------------------------------------
            *   `pos1` – Current (y, x) coordinate tuple."""

            return abs(pos1[0] - target_pos[0]) + abs(pos1[1] - target_pos[1])

        open_set: list[tuple[int, tuple[int, int]]] = []
        heappush(open_set, (0, start_pos))

        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score = {start_pos: 0}
        f_score = {start_pos: manhattan_distance(start_pos)}

        while open_set:
            current = heappop(open_set)[1]

            if current == goal_pos:
                return self._reconstruct_path(came_from, current, start_pos)

            current_g = g_score[current]
            y, x = current

            for dy, dx in directions:
                ny, nx = y + dy, x + dx

                if not (0 <= ny < height and 0 <= nx < width and self.maze[ny][nx] != self.wall_byte):
                    continue

                neighbor = (ny, nx)
                tentative_g_score = current_g + 1

                if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_value = tentative_g_score + manhattan_distance(neighbor)
                    f_score[neighbor] = f_value
                    heappush(open_set, (f_value, neighbor))

        return set()

    def _play_finish_animation(self, /, *, duration: float = 4.0, noise: float = 30.0, fps: int = 24) -> None:
        """Play an animated circular dissolve expanding outward from the goal position.\n
        ----------------------------------------------------------------------------------------------------
        *   `duration` – Total duration of the animation in seconds.
        *   `noise` – Noise percentage (0–100) introducing organic irregularity to the circle radius.
        *   `fps` – Target playback frame rate in frames per second."""

        start_time, noise_range = time.time(), noise / 100.0
        noise_map: dict[tuple[int, int], float] = {}
        min_noise, max_noise = 1 - noise_range, 1 + noise_range
        width, height = len(self.maze[0]), len(self.maze)
        max_distance = math.sqrt(height**2 + width**2)

        for y in range(height):
            for x in range(width):
                noise_map[y, x] = random.uniform(min_noise, max_noise)

        frame_delay = 1.0 / fps

        while time.time() - start_time < duration:
            elapsed = time.time() - start_time
            progress = elapsed / duration
            current_radius = progress * max_distance * 1.2

            for y in range(height):
                for x in range(width):
                    dist = math.sqrt((y - self.goal_pos[0]) ** 2 + (x - self.goal_pos[1]) ** 2)
                    if dist * noise_map.get((y, x), 1.0) < current_radius:
                        self.maze[y][x] = self.bg_byte

            self.render(output_to_console=True)
            time.sleep(frame_delay)

        for y in range(height):
            for x in range(width):
                self.maze[y][x] = self.bg_byte

        self.render(output_to_console=True)

    def render(self, /, *, output_to_console: bool = False, show_solution: bool = False) -> str | None:
        """Render the maze grid into a string or write it directly to the terminal screen.\n
        ----------------------------------------------------------------------------------------------------
        *   `output_to_console` – Whether to print the frame directly to stdout at cursor home position.
        *   `show_solution` – Whether to highlight tiles along the optimal solution path."""

        if self.show_solution or show_solution:
            solution_path = self._find_path(self.player_byte, self.goal_byte)
        else:
            solution_path: set[tuple[int, int]] = set()

        maze_lines: list[str] = []

        for y, row in enumerate(self.maze):
            line_parts: list[str] = []

            for x, cell in enumerate(row):
                if (self.show_solution or show_solution) and ((y, x) in solution_path and cell == self.bg_byte):
                    line_parts.append(self.rendered_tiles.get(self.solution_byte, ""))
                else:
                    line_parts.append(self.rendered_tiles.get(cell, self.rendered_tiles.get(self.bg_byte, "")))

            maze_lines.append("".join(line_parts))

        if output_to_console:
            sys.stdout.write(f"\033[H{'\n'.join(maze_lines)}")
            sys.stdout.flush()
        else:
            return "\n".join(maze_lines)

    def _game_main_loop(self) -> None:
        """Run the primary interactive loop, reading user inputs and updating state until finished."""

        wait = 0.0

        while not self.goal_reached:
            self.render(output_to_console=True)
            if wait > 0:
                time.sleep(wait)

            while not self.goal_reached:
                key = xx.console.read_key(raw=False)
                if len(key) == 1:
                    key = key.lower()

                if key in DIRECTIONS:
                    self._move_player(*DIRECTIONS[key])
                    if self.player_pos[0] == self.goal_pos[0] and self.player_pos[1] == self.goal_pos[1]:
                        self.goal_reached, self.show_solution = True, False
                        self._play_finish_animation()
                    wait = 0.05
                    break

                if key == "h":
                    self.show_solution = not self.show_solution
                    wait = 0.2
                    break

                if key == "f":
                    self.goal_reached, self.show_solution = True, False
                    self._play_finish_animation()
                    break


def main() -> None:
    """Display the title banner, handle user mode selection, and launch interactive maze play."""

    def smart_split(text: str, char: str = " ", /) -> list[str]:
        """Split a string by delimiter if present, or split by whitespace as a fallback.\n
        ----------------------------------------------------------------------------------------------------
        *   `text` – Input text to split.
        *   `char` – Delimiter character to split on."""

        cleaned = text.lower().strip()
        return cleaned.split(char) if char in cleaned else cleaned.split()

    xx.console.box(
        S.BR.BLUE(S.BOLD("  WASD ⏶⏴⏷⏵   "), S.BLUE(":"), " move the player"),
        S.BR.BLUE(S.BOLD("      H       "), S.BLUE(":"), " toggle solution"),
        S.BR.BLUE(S.BOLD("      F       "), S.BLUE(":"), " finish maze"),
        S.BR.BLUE(S.BOLD("   Ctrl", S.DIM("+"), "C     "), S.BLUE(":"), " exit game"),
        "{hr}",
        S.BR.BLUE(S.BOLD("    Enter     "), S.BLUE(":"), " start game normal"),
        S.BR.BLUE(S.BOLD(" Ctrl", S.DIM("+"), "Enter   "), S.BLUE(":"), " start game ASCII "),
        S.BR.BLUE(S.BOLD("    Space     "), S.BLUE(":"), " generate to file"),
        border_style=S.DIM | S.BR.BLUE,
        start="\n",
        end="\n\n",
    )

    while True:
        key = xx.console.read_key()

        if (ascii_mode := key.lower() in CTRL_ENTER_KEYS) or key in ENTER_KEYS:
            try:
                with xx.console.raw_mode():
                    while True:
                        Maze(xx.console.get_width() // 2, xx.console.get_height(), render_ascii=ascii_mode).play()

            except KeyboardInterrupt as exc:
                print("\x1bc\x1b[<u\x1b[>4;0m\x1b[?25h\x1b[0m", end="", flush=True)
                raise SystemExit(0) from exc

        elif key in KEYS.SPACEBAR:
            width, height = (
                int(num.strip())
                for num in smart_split(
                    S(
                        S.BR.CYAN("What dimensions should the maze be? ", S.DIM("(", S.ITALIC("25x25"), ")")),
                        S.DIM("\n ⤷ "),
                    )
                    .input()
                    .strip()
                    or "25x25",
                    "x",
                )
            )

            if width < 7 or height < 7:
                S(S.BR.RED("\n ", S.DIM("✗"), " Maze width/height can't be smaller than ", S.BOLD("7"), "\n")).print()
                raise SystemExit(1)

            dir_path = (
                Path(input_path)
                if len(
                    input_path := S(
                        S.BR.CYAN(
                            "In which directory should the maze files be saved? ",
                            S.DIM("(", S.ITALIC("script directory"), ")"),
                        ),
                        S.DIM("\n ⤷ "),
                    )
                    .input()
                    .strip()
                )
                > 0
                else xx.fs.get_script_dir()
            )

            files = (dir_path / f"maze_{width}x{height}.txt", dir_path / f"maze_{width}x{height}_solution.txt")

            print()

            with Throbber(
                format=[(S.DIM | S.BR.BLUE)("{a}"), S.BR.BLUE("{l}")],
                frames=("⠴", "⠦", "⠖", "⠲"),
                interval=0.1,
            ).context() as update_label:
                update_label("Generating maze")
                maze = Maze(width, height, render_ascii=True)
                info = (
                    f"═════ MAZE [{width}×{height}] TILES ═════\n"
                    + f"│ START = {maze.rendered_tiles[maze.player_byte]}\n"
                    + f"│ GOAL  = {maze.rendered_tiles[maze.goal_byte]}\n\n"
                )

                update_label("Rendering maze")
                maze.show_solution = False
                content = info + (maze.render() or "")

                update_label("Writing maze file")
                with open(files[0], "w", encoding="utf-8") as file:
                    file.write(content)

                update_label("Rendering solution")
                maze.show_solution = True
                content = info + (maze.render() or "")

                update_label("Writing solution file")
                with open(files[1], "w", encoding="utf-8") as file:
                    file.write(content)

                update_label("Finalizing")
                sizes: list[str] = []

                for file_path in files:
                    file_size = Path(file_path).stat().st_size
                    unit_str = "B"

                    for i, unit in enumerate(["B", "KB", "MB", "GB", "TB"]):
                        if file_size < 1024 ** (i + 1):
                            unit_str = f"{file_size / 1024**i:.1f} {unit}"
                            break

                    sizes.append(unit_str)

            xx.console.box(
                S.BR.BLUE(
                    "Saved maze to ",
                    (S.BOLD | S.link(files[0]))(files[0].name),
                    S.DIM(" [", S.ITALIC(sizes[0]), "]"),
                ),
                S.BR.BLUE(
                    "Saved solution to ",
                    (S.BOLD | S.link(files[1]))(files[1].name),
                    S.DIM(" [", S.ITALIC(sizes[1]), "]"),
                ),
                border_style=S.DIM | S.BR.BLUE,
                end="\n\n",
            )

            break


if __name__ == "__main__":
    args = ArgumentParser(
        title="Maze",
        subtitle="Play a maze game or generate mazes in the terminal",
        controls=[
            ("Enter", "Start game in normal mode"),
            ("Ctrl+Enter", "Start game in ASCII mode"),
            ("Space", "Generate maze to a file"),
            (("WASD", "⏶⏴⏷⏵"), "Move the player"),
            ("H", "Toggle solution path"),
            ("F", "Finish maze"),
            ("Ctrl+C", "Exit game"),
        ],
        examples=[("{cmd}", "Start the interactive maze game")],
    )

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print("\x1b[<u\x1b[>4;0m\x1b[?25h\x1b[0m", end="", flush=True)

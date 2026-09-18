#!/usr/bin/env python3
# ruff:file-ignore[ambiguous-unicode-character-string]
# x-tools:file[update]

"""
Conway's game of life in the console.
"""

import random
import sys
import time
import xulbux as xx
from xulbux import ArgumentParser, S
from xulbux.base.consts import CHARS


class GameOfLife:
    def __init__(self) -> None:
        self.width: int = xx.console.get_width()
        self.height: int = xx.console.get_height() * 2
        self.grid = [[False for _ in range(self.width)] for _ in range(self.height)]
        self.next_grid = [[False for _ in range(self.width)] for _ in range(self.height)]

        # Pre-compute UTF-8 byte sequences for maximum efficiency:
        self.c_full: bytes = "█".encode()
        self.c_upper: bytes = "▀".encode()
        self.c_lower: bytes = "▄".encode()
        self.c_empty: bytes = b" "

    def initialize_random(self, density: float = 0.3) -> None:
        for y in range(self.height):
            for x in range(self.width):
                self.grid[y][x] = random.random() < density

    def count_neighbors(self, x: int, y: int) -> int:
        count = 0

        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue

                nx, ny = x + dx, y + dy

                if 0 <= nx < self.width and 0 <= ny < self.height and self.grid[ny][nx]:
                    count += 1

        return count

    def update(self) -> None:
        for y in range(self.height):
            for x in range(self.width):
                neighbors = self.count_neighbors(x, y)
                current_state = self.grid[y][x]

                if current_state:
                    self.next_grid[y][x] = neighbors in [2, 3]
                else:
                    self.next_grid[y][x] = neighbors == 3

        self.grid, self.next_grid = self.next_grid, self.grid

    def render(self) -> None:
        frame = bytearray()
        for i, row in enumerate(range(0, self.height - 1, 2)):
            line = bytearray()

            for col in range(self.width):
                upper_filled = self.grid[row][col]
                lower_filled = self.grid[row + 1][col]

                if upper_filled and lower_filled:
                    char_bytes = self.c_full
                elif upper_filled:
                    char_bytes = self.c_upper
                elif lower_filled:
                    char_bytes = self.c_lower
                else:
                    char_bytes = self.c_empty

                line.extend(char_bytes)

            frame.extend(line)

            if i < (self.height - 1) // 2 - 1:
                frame.extend(b"\n")

        sys.stdout.write(f"\x1bc{frame.decode('utf-8')}")

    def add_glider(self, x: int, y: int) -> None:
        glider = [[False, True, False], [False, False, True], [True, True, True]]

        for dy in range(3):
            for dx in range(3):
                nx, ny = x + dx, y + dy

                if 0 <= nx < self.width and 0 <= ny < self.height:
                    self.grid[ny][nx] = glider[dy][dx]

    def add_oscillator(self, x: int, y: int) -> None:
        if 0 <= x < self.width and 0 <= y - 1 < self.height and 0 <= y + 1 < self.height:
            self.grid[y - 1][x] = True
            self.grid[y][x] = True
            self.grid[y + 1][x] = True

    def run(self, gens: int | None = None, delay: float = 0.05) -> None:
        try:
            gen = 0
            while gens is None or gen < gens:
                new_width: int = xx.console.get_width()
                new_height: int = xx.console.get_height() * 2

                if new_width != self.width or new_height != self.height:
                    old_grid = self.grid

                    self.width = new_width
                    self.height = new_height
                    self.grid = [[False for _ in range(self.width)] for _ in range(self.height)]
                    self.next_grid = [[False for _ in range(self.width)] for _ in range(self.height)]

                    for y in range(min(len(old_grid), self.height)):
                        for x in range(min(len(old_grid[0]), self.width)):
                            self.grid[y][x] = old_grid[y][x]

                self.render()
                self.update()
                gen += 1
                time.sleep(delay)

        except KeyboardInterrupt:
            sys.stdout.write("\x1bc")


def main() -> None:
    game = GameOfLife()

    S(
        S.BOLD("Choose Initialization"),
        ((S.BOLD | S.ITALIC)(" 1  "), "Random pattern"),
        ((S.BOLD | S.ITALIC)(" 2  "), "Some classic patterns"),
        sep="\n",
    ).print()

    choice = xx.console.input(("(1) ", S.BOLD(">"), " "), max_len=1, allowed_chars="12", default_val=1, output_type=int)

    match choice:
        case 2:
            game.add_glider(5, 5)
            game.add_glider(15, 8)
            game.add_oscillator(25, 10)
            game.add_oscillator(30, 15)

            for _ in range(20):
                x = random.randint(0, game.width - 1)
                y = random.randint(0, game.height - 1)
                game.grid[y][x] = True

        case _:
            density = 0.2
            density = xx.console.input(
                (S.BOLD("\nEnter density"), f" [0.0 – 1.0]({density}) ", S.BOLD(">"), " "),
                allowed_chars=CHARS.FLOAT_DIGITS,
                default_val=density,
                output_type=float,
            )
            game.initialize_random(max(0.0, min(1.0, density)))

    delay = 0.02
    delay = xx.console.input(
        (S.BOLD("\nDelay between generations"), f" [secs]({delay}) ", S.BOLD(">"), " "),
        allowed_chars=CHARS.FLOAT_DIGITS,
        default_val=delay,
        output_type=float,
    )

    game.run(delay=max(0, delay))


if __name__ == "__main__":
    args = ArgumentParser(
        title="Game of Life",
        subtitle="Conway's cellular automaton in the terminal",
        controls=[("Ctrl+C", "Exit the simulation")],
        examples=[("{cmd}", "Start Game of Life with interactive setup")],
    )

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

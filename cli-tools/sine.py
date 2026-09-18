#!/usr/bin/env python3
# x-tools:file[update]

"""
Show a sine wave animation inside the terminal.
"""

import math
import time
import xulbux as xx
from xulbux import ArgumentParser, S


def show_wave(width: int, speed: tuple[float, float] = (5, 1)) -> None:
    t = 0
    half_w = width // 2
    prev_x: int | None = None

    def wave_x(step: float) -> int:
        return max(0, min(width - 1, int(half_w * math.sin(math.radians(step * speed[0])) + half_w)))

    while True:
        x1 = wave_x(t)  # Upper half of this terminal row.
        x2 = wave_x(t + 0.5)  # Lower half of this terminal row.

        # Upper half: connect from previous position to x1:
        lo_u = min(prev_x, x1) if prev_x is not None else x1
        hi_u = max(prev_x, x1) if prev_x is not None else x1
        # Lower half: connect from x1 to x2:
        lo_l, hi_l = min(x1, x2), max(x1, x2)

        line: list[str] = []
        for col in range(width):
            upper = lo_u <= col <= hi_u
            lower = lo_l <= col <= hi_l
            if upper and lower:
                c = "█"
            elif upper:
                c = "▀"
            elif lower:
                c = "▄"
            else:
                c = " "
            line.append(c)

        print("".join(line))

        prev_x = x2
        t += 1

        time.sleep(1 / (speed[1] * 100))


def main() -> None:
    speed = max(0.1, ARGS.speed.val(float, default=1.0))
    y_stretch = max(0.1, ARGS.y_stretch.val(float, default=1.0))

    show_wave(width=xx.console.get_width() - 1, speed=(2 / y_stretch, speed))


if __name__ == "__main__":
    args = ArgumentParser(
        title="Sine",
        subtitle="Show a sine wave animation inside the terminal",
        controls=[("Ctrl+C", "Stop the animation")],
        examples=[
            ("{cmd}", "Default wave"),
            ("{cmd} --speed=2", "Scroll twice as fast"),
            ("{cmd} --y-stretch=3", "Cycles 3× more stretched out"),  # ruff:ignore[ambiguous-unicode-character-string]
            ("{cmd} -s=0.5 -y=0.5", "Half speed, half stretch"),
        ],
    )

    args.add_opt(
        {"-s", "--speed"},
        expects_value="N",
        help=("Animation speed multiplier ", S.DIM("(default: 1.0)")),
    )
    args.add_opt(
        {"-y", "--y-stretch"},
        expects_value="N",
        help=("Vertical stretch of wave cycles ", S.DIM("(default: 1.0)")),
    )

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

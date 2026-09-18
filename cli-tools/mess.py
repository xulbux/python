#!/usr/bin/env python3
# x-tools:file[update]

"""
Displays an animated, random text character mess.
The mess can be made faster and displayed in color.
"""

import random as rnd
import time
import xulbux as xx
from xulbux import ArgumentParser
from xulbux.ansi import AnyStyle, S

digits: list[str] = ["0", "1"]
styles: list[AnyStyle] = [S.DIM, S.BOLD, S.INVERSE, S.UNDERLINE, S.STRIKETHROUGH, S.DOUBLE_UNDERLINE]


def binary_line() -> S:
    return S(*(rnd.choice(styles)(rnd.choice(digits)) for _ in range(xx.console.get_width())))


def main() -> None:
    # fmt: off
    if ARGS.color_mode.exists:
        styles.extend([
            S.BLACK, S.RED, S.GREEN, S.YELLOW, S.BLUE, S.MAGENTA, S.CYAN, S.WHITE,
            S.BR.BLACK, S.BR.RED, S.BR.GREEN, S.BR.YELLOW, S.BR.BLUE, S.BR.MAGENTA, S.BR.CYAN, S.BR.WHITE,
            S.BG.BLACK, S.BG.RED, S.BG.GREEN, S.BG.YELLOW, S.BG.BLUE, S.BG.MAGENTA, S.BG.CYAN, S.BG.WHITE,
            S.BG.BR.BLACK, S.BG.BR.RED, S.BG.BR.GREEN, S.BG.BR.YELLOW, S.BG.BR.BLUE, S.BG.BR.MAGENTA, S.BG.BR.CYAN, S.BG.BR.WHITE,  # ruff:ignore[line-too-long]
        ])
    # fmt: on

    if ARGS.fast_mode.exists:
        while True:
            binary_line().print()
    else:
        while True:
            binary_line().print()
            time.sleep(0.025)


if __name__ == "__main__":
    args = ArgumentParser(
        title="Mess",
        subtitle="Display a random binary mess",
        controls=[("Ctrl+C", "Stop the animation")],
        examples=[
            ("{cmd}", "Show binary mess at normal speed"),
            ("{cmd} -c -f", "Show colorful binary mess at maximum speed"),
        ],
    )

    args.add_opt({"-c", "--color"}, "color_mode", help="Color the mess in random colors")
    args.add_opt({"-f", "--fast"}, "fast_mode", help="Display the mess at maximum speed")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

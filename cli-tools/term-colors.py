#!/usr/bin/env python3
# x-tools:file[update]

"""
Show the foreground and background colors
from the current terminal color scheme.
"""

from xulbux import ArgumentParser, S
from xulbux.ansi import AnyStyle

SHELL_COLORS: list[list[AnyStyle]] = [
    [S.BLACK, S.BR.BLACK, S.WHITE | S.BG.BLACK, S.WHITE | S.BG.BR.BLACK],
    [S.WHITE, S.BR.WHITE, S.BLACK | S.BG.WHITE, S.BLACK | S.BG.BR.WHITE],
    [S.RED, S.BR.RED, S.BLACK | S.BG.RED, S.BLACK | S.BG.BR.RED],
    [S.YELLOW, S.BR.YELLOW, S.BLACK | S.BG.YELLOW, S.BLACK | S.BG.BR.YELLOW],
    [S.GREEN, S.BR.GREEN, S.BLACK | S.BG.GREEN, S.BLACK | S.BG.BR.GREEN],
    [S.CYAN, S.BR.CYAN, S.BLACK | S.BG.CYAN, S.BLACK | S.BG.BR.CYAN],
    [S.BLUE, S.BR.BLUE, S.BLACK | S.BG.BLUE, S.BLACK | S.BG.BR.BLUE],
    [S.MAGENTA, S.BR.MAGENTA, S.BLACK | S.BG.MAGENTA, S.BLACK | S.BG.BR.MAGENTA],
]


def show_shell_colors() -> None:
    norm_fg, bright_fg, norm_bg, bright_bg = zip(*SHELL_COLORS, strict=False)
    output = S("\n")

    for fgs, bgs in [(norm_fg, norm_bg), (bright_fg, bright_bg)]:
        output += "  "
        for fmt in fgs:
            output += (fmt("Aa"), " ")
        output += "  "
        for fmt in bgs:
            output += fmt(" Aa ")
        output += "\n"

    output.print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="Terminal Colors",
        subtitle="Show all foreground and background terminal colors",
    )

    global ARGS
    ARGS = args.parse()

    show_shell_colors()

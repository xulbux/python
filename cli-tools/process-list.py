#!/usr/bin/env python3
# x-tools:file[update]

"""
Process a list of items and display some statistics.
"""

import xulbux as xx
from xulbux import ArgumentParser, S


def avg(nums: list[int | float]) -> float:
    return sum(nums) / len(nums)


def main() -> None:
    clean_items = [item for item in " ".join(ARGS.items.vals()).split(ARGS.separator.val()) if item.strip() not in {"", None}]

    if len(clean_items) >= 1 and clean_items[0].strip() not in {"", None}:
        title = S((S.INVERSE | S.BG.hex("000"))("  Processed ", S.BOLD(str(len(clean_items))), " list entries  "))
        S(
            "",
            "▄" * len(title.raw),
            title,
            "▀" * len(title.raw),
            "",
            S.BR.CYAN("\n".join(clean_items)),
            "",
            sep="\n",
        ).print()

        if all(item.isnumeric() for item in clean_items):
            clean_items = [int(item) if item.replace("_", "").isdigit() else float(item) for item in clean_items]

            xx.console.box(
                (S.BOLD("Min"), S.DIM(" : "), S.BR.CYAN(str(min(clean_items)))),
                (S.BOLD("Max"), S.DIM(" : "), S.BR.CYAN(str(max(clean_items)))),
                (S.BOLD("Sum"), S.DIM(" : "), S.BR.CYAN(str(sum(clean_items)))),
                (S.BOLD("Avg"), S.DIM(" : "), S.BR.CYAN(str(avg(clean_items)))),
                border_style=S.DIM,
            )

        else:
            clean_items = [str(item) for item in clean_items]
            box_content = S(
                S.BOLD("Unique entries"),
                S.DIM(" : "),
                S(" ").join((S.BR.CYAN | S.BG.hex("000"))(item) for item in sorted(set(clean_items))),
            )

            if any(not item.replace("_", "").isdigit() for item in clean_items):
                upper = sum(1 for item in clean_items if item.isupper())
                lower = sum(1 for item in clean_items if item.islower())
                box_content += ("\n", S.BOLD("Uppercase"), S.DIM("      : "), f"{upper / len(clean_items) * 100:.1f}%")
                box_content += ("\n", S.BOLD("Lowercase"), S.DIM("      : "), f"{lower / len(clean_items) * 100:.1f}%")

            xx.console.box(box_content, border_style=S.DIM)

        print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="Process List",
        subtitle="Process a list of items and display statistics",
        examples=[
            ("{cmd} 1 2 3 4 5", "Process a list of numbers"),
            ("{cmd} a b c", "Process a list of strings"),
            ('{cmd} "1,2,3" -s=","', "Process comma-separated values"),
        ],
        epilog=S(
            S.BOLD("Note:  "),
            "When all items are numbers, min, max, sum and average are also shown.",
        ),
    )

    args.add_arg(
        "items",
        nargs="+",
        help=("List items to process ", S.DIM("(space-separated or custom separator using ", S.BR.BLUE("-s"), ")")),
    )
    args.add_opt(
        {"-s", "--sep"},
        "separator",
        expects_value="S",
        help="Separator character to split a single input string",
    )

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

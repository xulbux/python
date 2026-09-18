#!/usr/bin/env python3
# x-tools:file[update]

"""
Generate a truly random number with a specific number of digits or within a range.
Provide either the number of digits or a min and max range.
"""

import secrets
import sys
import xulbux as xx
from xulbux import ArgumentParser, ProgressBar, S

sys.set_int_max_str_digits(0)  # 0 = no limit.


def gen_random_int(*, digits: int | None = None, min_val: int | None = None, max_val: int | None = None) -> int:
    """Generate a truly random integer with a specific number of digits or within a range."""

    # Random number with specific amount of digits:
    if digits is not None:
        if digits <= 0:
            raise ValueError("The number of decimal places must be a positive integer.")
        random_int = secrets.randbelow((10**digits - 1) - (min_value := 10 ** (digits - 1)) + 1) + min_value

    # Random number within a specified range:
    elif min_val is not None and max_val is not None:
        if min_val >= max_val:
            raise ValueError("The minimum value must be less than the maximum value.")
        random_int = secrets.randbelow(max_val - min_val + 1) + min_val

    # Invalid usage:
    else:
        raise ValueError("Either 'digits' or both 'min_val' and 'max_val' must be provided.")

    return random_int


def main() -> None:
    print()

    batch = ARGS.batch_gen.val(int, default=1)
    t_sep = "," if ARGS.format.exists else ""

    if not ARGS.number_2.exists:
        digits = ARGS.number.val(int)
        S.DIM("generating...").print(end="")

        if batch > 1:
            random_ints: list[str] = []

            # Batch generate random integers:
            with ProgressBar().progress_context(batch, "generating...") as update_progress:
                update_progress(0)
                for i in range(batch):
                    random_int = gen_random_int(digits=digits)
                    random_ints.append(f"{random_int:{t_sep}}")
                    update_progress(i + 1)

            S("\x1b[2K\r", S.DIM("formatting...")).print(end="")
            S("\x1b[2K\r", S.BR.BLUE("\n".join(random_ints)), "\n").print()

        else:
            random_int = gen_random_int(digits=digits)
            S("\x1b[2K\r", S.BR.BLUE(f"{random_int:{t_sep}}"), "\n").print()

    else:
        min_val = ARGS.number.val(int, 0)
        max_val = ARGS.number_2.val(int, 0)

        if min_val >= max_val:
            xx.console.exit(
                (S.BOLD("Invalid range: "), "The minimum value must be less than the maximum value"),
                end="\n\n",
                exit_code=1,
            )

        S.DIM("generating...").print(end="")

        if batch > 1:
            random_ints, lowest_int, highest_int = [], max_val + 1, min_val - 1

            with ProgressBar().progress_context(batch, "generating...") as update_progress:
                for i in range(batch):
                    random_int = gen_random_int(min_val=min_val, max_val=max_val)
                    random_ints.append(f"{random_int:{t_sep}}")
                    if random_int < lowest_int:
                        lowest_int = random_int
                    if random_int > highest_int:
                        highest_int = random_int
                    update_progress(i + 1)

            S("\x1b[2K\r", S.DIM("formatting...")).print(end="")
            S("\x1b[2K\r", S.BR.BLUE("\n".join(random_ints))).print()
            S(
                "",
                ((S.BOLD | S.DIM)("lowest:"), f"  {'' if lowest_int < 0 else ' '}", S.DIM(f"{lowest_int:{t_sep}}")),
                ((S.BOLD | S.DIM)("highest:"), f" {'' if highest_int < 0 else ' '}", S.DIM(f"{highest_int:{t_sep}}")),
                "",
                sep="\n",
            ).print()

        else:
            random_int = gen_random_int(min_val=min_val, max_val=max_val)
            S("\x1b[2K\r", S.BR.BLUE(f"{random_int:{t_sep}}"), "\n").print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="Random",
        subtitle="Generate truly random numbers",
        examples=[
            ("{cmd} 10", "Random number with 10 digits"),
            ("{cmd} -100 100", "Random number between -100 and 100"),
            ("{cmd} 5 --batch-gen=3", "3 random numbers with 5 digits"),
            ("{cmd} 10 --format", "Comma-formatted random number with 10 digits"),
        ],
    )

    args.add_arg("number", help="Number of digits or start of range")
    args.add_arg("number_2", required=False, help=("End of range ", S.DIM("(optional)")))
    args.add_opt(
        {"-b", "--batch", "--batch-gen"},
        "batch_gen",
        expects_value="N",
        help="Generate multiple random numbers",
    )
    args.add_opt({"-f", "--format"}, help="Format numbers with commas as thousand separators")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        S("\x1b[2K\r", (S.BOLD | S.BR.RED)("✗"), "\n").print()
    except MemoryError:
        xx.console.fail(
            (S.BOLD("MemoryError: "), "The operation ran out of memory"),
            start="\x1b[2K\r",
            end="\n\n",
            exit_code=1,
        )
    except OverflowError as exc:
        xx.console.fail(
            (S.BOLD("OverflowError: "), exc),
            start="\x1b[2K\r",
            end="\n\n",
            exit_code=1,
        )
    except Exception as exc:
        xx.console.fail(
            exc,
            start="\x1b[2K\r",
            end="\n\n",
            exit_code=1,
        )

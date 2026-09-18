#!/usr/bin/env python3
# x-cmds:file[update]

"""
Calculate the value of π to a specified number of decimal places.
"""

import math
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING
import xulbux as xx
from xulbux import ArgumentParser, S, Throbber
from xulbux.console import FRAMES_WINDMILL

if TYPE_CHECKING:
    from xulbux.ansi import Renderable

REFERENCE_TIMES: dict[int, float] = {
    1000: 0.01,  # 1K digits
    5000: 0.175,  # 5K digits
    10000: 0.75,  # 10K digits
    25000: 5.10,  # 25K digits
    50000: 25,  # 50K digits
    100000: 120,  # 100K digits
    500000: 3000,  # 500K digits
    1000000: 75000,  # 1M digits
}


def get_hardware_score() -> float:
    try:
        import psutil

        cpu_freq = psutil.cpu_freq()
        max_freq = cpu_freq.max if cpu_freq else 3000
        cpu_count = psutil.cpu_count(logical=False) or 1
        memory = psutil.virtual_memory()
        memory_factor = 1 + (0.3 * (1 - memory.available / memory.total))
        return ((max_freq * math.sqrt(cpu_count)) / 4000) / memory_factor

    except (ImportError, AttributeError):
        # Fallback: use default hardware score (assumes modern mid-range system):
        return 1.0


def estimate_runtime(precision: int) -> float:
    ref_points = sorted(REFERENCE_TIMES.keys())

    if precision <= 100:
        start_time = time.time()
        _ = pi(precision)
        return time.time() - start_time

    if precision >= max(ref_points):
        base_time = REFERENCE_TIMES[max(ref_points)]
        scaling = (precision / max(ref_points)) ** 2.0
        if precision > 1000000:
            scaling *= 1.2

    else:
        upper_idx = next(i for i, x in enumerate(ref_points) if x >= precision)
        lower_idx = max(0, upper_idx - 1)
        lower_point = ref_points[lower_idx]
        upper_point = ref_points[upper_idx]
        lower_time = REFERENCE_TIMES[lower_point]
        upper_time = REFERENCE_TIMES[upper_point]

        if lower_point == upper_point:
            log_factor = 1
        else:
            raw_factor = precision / lower_point
            log_factor = (math.log(raw_factor) ** 2) / (math.log(upper_point / lower_point))

        base_time = lower_time * (upper_time / lower_time) ** log_factor
        scaling = 1.0

    estimated_time = (base_time * scaling) / get_hardware_score()

    if estimated_time < 0.01:
        estimated_time = 0.01
    if precision <= 5000:
        correction_factor = 1.0
    elif precision <= 10000:
        correction_factor = 1.5
    elif precision <= 25000:
        correction_factor = 1.8
    elif precision <= 50000:
        correction_factor = 1.0
    elif precision <= 100000:
        correction_factor = 0.9
    else:
        correction_factor = 1.0

    estimated_time *= correction_factor

    return round(estimated_time, 2)


def format_time(seconds: float, short: bool = False, pretty_print: bool = False) -> S:
    units = (
        (
            ("SMBH", 1e106 * 365.25 * 24 * 60 * 60),
            ("HD", 1e100 * 365.25 * 24 * 60 * 60),
            ("BH", 1e40 * 365.25 * 24 * 60 * 60),
            ("DE", 1e14 * 365.25 * 24 * 60 * 60),
            ("SE", 1e12 * 365.25 * 24 * 60 * 60),
            ("GY", 225e6 * 365.25 * 24 * 60 * 60),
            ("HT", 13.8e9 * 365.25 * 24 * 60 * 60),
            ("Q", 1e30 * 365.25 * 24 * 60 * 60),
            ("R", 1e27 * 365.25 * 24 * 60 * 60),
            ("Y", 1e24 * 365.25 * 24 * 60 * 60),
            ("Z", 1e21 * 365.25 * 24 * 60 * 60),
            ("E", 1e18 * 365.25 * 24 * 60 * 60),
            ("P", 1e15 * 365.25 * 24 * 60 * 60),
            ("T", 1e12 * 365.25 * 24 * 60 * 60),
            ("G", 1e9 * 365.25 * 24 * 60 * 60),
            ("M", 1e6 * 365.25 * 24 * 60 * 60),
            ("k", 1e3 * 365.25 * 24 * 60 * 60),
            ("y", 365.25 * 24 * 60 * 60),
            ("mo", 30 * 24 * 60 * 60),
            ("w", 7 * 24 * 60 * 60),
            ("d", 24 * 60 * 60),
            ("h", 60 * 60),
            ("m", 60),
            ("s", 1),
        ),
        (
            ("supermassive black hole lifespan", 1e106 * 365.25 * 24 * 60 * 60),
            ("universe heat death", 1e100 * 365.25 * 24 * 60 * 60),
            ("black hole era", 1e40 * 365.25 * 24 * 60 * 60),
            ("degenerate era", 1e14 * 365.25 * 24 * 60 * 60),
            ("stelliferous era", 1e12 * 365.25 * 24 * 60 * 60),
            ("galactic year", 225e6 * 365.25 * 24 * 60 * 60),
            ("Hubble time", 13.8e9 * 365.25 * 24 * 60 * 60),
            ("quetta-year", 1e30 * 365.25 * 24 * 60 * 60),
            ("ronna-year", 1e27 * 365.25 * 24 * 60 * 60),
            ("yotta-year", 1e24 * 365.25 * 24 * 60 * 60),
            ("zetta-year", 1e21 * 365.25 * 24 * 60 * 60),
            ("exa-year", 1e18 * 365.25 * 24 * 60 * 60),
            ("peta-year", 1e15 * 365.25 * 24 * 60 * 60),
            ("tera-year", 1e12 * 365.25 * 24 * 60 * 60),
            ("giga-year", 1e9 * 365.25 * 24 * 60 * 60),
            ("mega-year", 1e6 * 365.25 * 24 * 60 * 60),
            ("kilo-year", 1e3 * 365.25 * 24 * 60 * 60),
            ("year", 365.25 * 24 * 60 * 60),
            ("month", 30 * 24 * 60 * 60),
            ("week", 7 * 24 * 60 * 60),
            ("day", 24 * 60 * 60),
            ("hour", 60 * 60),
            ("minute", 60),
            ("second", 1),
        ),
    )

    parts: list[Renderable] = []

    b_val_st = S.BR.MAGENTA if pretty_print else ""
    val_name_st = ("" if short else " ", S.MAGENTA if pretty_print else "")
    a_name_st = S.BR.MAGENTA if pretty_print else ""
    r_st = S.RESET if pretty_print else ""

    for name, formula in units[0 if short else 1]:
        if (val := int(seconds // formula)) > 0:
            if not short:
                val = f"{val:,}"
            parts.append((
                b_val_st,
                str(val),
                r_st,
                val_name_st,
                name if val == "1" or short else f"{name}s",
                r_st,
                a_name_st,
            ))
            seconds %= formula

    if not parts:
        parts.append((
            b_val_st,
            f"{f'{seconds:.3f}'.rstrip('0').rstrip('.')}",
            r_st,
            val_name_st,
            (units[0 if short else 1][-1][0] if seconds == 1 or short else f"{units[0 if short else 1][-1][0]}s"),
            r_st,
            a_name_st,
        ))

    if short:
        return S(" ").join(parts)

    if len(parts) > 1:
        return (
            (S.DIM(", ") if pretty_print else S(", ")).join(parts[:-1]) + (S.DIM(" & ") if pretty_print else " & ") + parts[-1]
        )

    return S(parts[0])


def pi_generator() -> Iterator[int]:
    q, r, t, j = 1, 180, 60, 2
    while True:
        u, y = 3 * (3 * j + 1) * (3 * j + 2), (q * (27 * j - 12) + 5 * r) // (5 * t)
        yield y
        q, r, t, j = (10 * q * j * (2 * j - 1), 10 * u * (q * (5 * j - 2) + r - y * t), t * u, j + 1)


def pi(decimals: int = 10) -> str:
    pi_gen = pi_generator()
    return "3." + "".join(str(next(pi_gen)) for _ in range(decimals + 1))[1:]


def main() -> None:
    input_k = int(v.replace("_", "")) if (v := ARGS.decimals.val()) and v.replace("_", "").isdigit() else 10

    if (estimated_secs := estimate_runtime(input_k)) >= 604800:
        S(
            (S.BOLD | S.BG.hex("000"))("\n π ", S.INVERSE(" Calculation would take too long \n")),
            (f"\n{format_time(estimated_secs, pretty_print=True)}\n", S.RESET),
        ).print()

    else:
        S(
            S.DIM("\nWill take about ", S.BOLD(format_time(estimated_secs)), " to calculate:") if estimated_secs > 1 else ""
        ).print()

        result = None

        try:
            with Throbber(frames=FRAMES_WINDMILL).context():
                result = pi(input_k)
        except MemoryError:
            S(
                (S.BOLD | S.BR.YELLOW)("\rYour computer doesn't have enough memory for this calculation!"),
                (S.BOLD | S.BG.hex("000"))(
                    "\n π ", S.INVERSE(" Calculation would take this long if you had enough memory \n")
                ),
                (format_time(estimated_secs, pretty_print=True), S.RESET, "\n"),
                sep="\n",
            ).print()
        except KeyboardInterrupt as exc:
            S((S.BOLD | S.BR.RED)("\r✗"), "  \n").print()
            raise SystemExit(0) from exc

        if result:
            S((S.BOLD | S.BR.CYAN)("\r", result), "\n").print()
        else:
            S((S.BOLD | S.BR.RED)("\r✗"), "  \n").print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="Pi",
        subtitle="Calculate the value of π to a specified number of decimal places",
        examples=[
            ("{cmd}", "Calculate π to 10 decimal places"),
            ("{cmd} 10_000", "Calculate π to 10,000 decimal places"),
        ],
    )

    args.add_arg("decimals", required=False, help="Number of decimal places (default: 10)")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

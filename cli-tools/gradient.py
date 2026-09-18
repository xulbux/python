#!/usr/bin/env python3
# x-tools:file[update]

"""
Quickly generate and preview a color gradient for a
specified color channel with a specified number of steps.
"""

import colorsys
from typing import TYPE_CHECKING, Literal, cast
import xulbux as xx
from xulbux import ArgumentParser, S, hexa, rgba

if TYPE_CHECKING:
    from xulbux.ansi import RenderSegment


def interpolate_oklch(
    color_1: rgba,
    color_2: rgba,
    t: float,
    hue_direction: Literal["shortest", "clockwise", "counterclockwise"] = "shortest",
) -> rgba:
    """Interpolate between two colors using OKLCH color space for perceptual uniformity.\n
    ----------------------------------------------------------------------------------------------------
    - `color_1` – Starting RGBA color.
    - `color_2` – Ending RGBA color.
    - `t` – Interpolation factor (0.0 to 1.0).
    - `hue_direction` – Direction for hue interpolation (shortest, clockwise, counterclockwise)."""

    try:
        import numpy as np
        from colorspacious import cspace_convert  # pyright:ignore[reportMissingTypeStubs,reportUnknownVariableType]

    except ImportError as exc:
        raise ImportError(
            S(
                "OKLCH mode requires NumPy and colorspacious, but they are not compatible with your Python version.",
                (
                    "Please use ",
                    S.BR.BLUE("--hsv"),
                    " mode instead, or downgrade your Python to a version that supports these packages.",
                ),
                sep="\n",
            )
        ) from exc

    # Convert RGB (0-255) to SRGB (0-1):
    rgb_a = np.array([color_1[0] / 255.0, color_1[1] / 255.0, color_1[2] / 255.0])
    rgb_b = np.array([color_2[0] / 255.0, color_2[1] / 255.0, color_2[2] / 255.0])

    # Convert SRGB to OKLCH (using CAM02-UCS / JCh which is similar to OKLCH):
    oklch_a = cast("np.ndarray", cspace_convert(rgb_a, "sRGB1", "JCh"))
    oklch_b = cast("np.ndarray", cspace_convert(rgb_b, "sRGB1", "JCh"))

    # Interpolate in OKLCH space:
    L = oklch_a[0] + (oklch_b[0] - oklch_a[0]) * t
    C = oklch_a[1] + (oklch_b[1] - oklch_a[1]) * t

    # Interpolate hue based on direction:
    h1, h2 = oklch_a[2], oklch_b[2]

    if hue_direction == "shortest":
        # Use shortest path:
        if (diff := h2 - h1) > 180:
            diff -= 360
        elif diff < -180:
            diff += 360

    elif hue_direction == "clockwise":
        # Force clockwise (longer path if h2 < h1):
        if (diff := h2 - h1) < 0:
            diff += 360

    elif hue_direction == "counterclockwise":
        # Force counterclockwise (longer path if h2 > h1):
        if (diff := h2 - h1) > 0:
            diff -= 360

    else:
        diff = h2 - h1

    h = (h1 + diff * t) % 360

    # Convert back to SRGB:
    oklch_interpolated = np.array([L, C, h])
    rgb_interpolated = cast("np.ndarray", cspace_convert(oklch_interpolated, "JCh", "sRGB1"))

    # Clamp to valid RGB range and convert to 0-255:
    rgb_interpolated = np.clip(rgb_interpolated, 0, 1)
    r = round(rgb_interpolated[0] * 255)
    g = round(rgb_interpolated[1] * 255)
    b = round(rgb_interpolated[2] * 255)

    return rgba(r, g, b)


def interpolate_hsv(
    color_1: rgba,
    color_2: rgba,
    t: float,
    hue_direction: Literal["shortest", "clockwise", "counterclockwise"] = "shortest",
) -> rgba:
    """Interpolate between two colors using HSV color space with directional hue rotation.\n
    ----------------------------------------------------------------------------------------------------
    - `color_1` – Starting RGBA color.
    - `color_2` – Ending RGBA color.
    - `t` – Interpolation factor (0.0 to 1.0).
    - `hue_direction` – Direction for hue interpolation (shortest, clockwise, counterclockwise)."""

    # Convert RGB to HSV (hue 0-1, saturation 0-1, value 0-1):
    h1, s1, v1 = colorsys.rgb_to_hsv(color_1[0] / 255.0, color_1[1] / 255.0, color_1[2] / 255.0)
    h2, s2, v2 = colorsys.rgb_to_hsv(color_2[0] / 255.0, color_2[1] / 255.0, color_2[2] / 255.0)

    # Convert hue to degrees (0-360):
    h1_deg = h1 * 360
    h2_deg = h2 * 360

    # Interpolate hue based on direction:
    if hue_direction == "shortest":
        # Use shortest path:
        if (diff := h2_deg - h1_deg) > 180:
            diff -= 360
        elif diff < -180:
            diff += 360

    elif hue_direction == "clockwise":
        # Force clockwise:
        if (diff := h2_deg - h1_deg) < 0:
            diff += 360

    elif hue_direction == "counterclockwise":
        # Force counterclockwise:
        if (diff := h2_deg - h1_deg) > 0:
            diff -= 360

    else:
        diff = h2_deg - h1_deg

    h_deg = (h1_deg + diff * t) % 360

    # Interpolate saturation and value:
    s = s1 + (s2 - s1) * t
    v = v1 + (v2 - v1) * t

    # Convert back to RGB:
    r, g, b = colorsys.hsv_to_rgb(h_deg / 360.0, s, v)

    # Convert to 0-255 range:
    return rgba(round(r * 255), round(g * 255), round(b * 255))


def generate_multi_gradient(
    colors: list[rgba],
    directions: list[Literal["shortest", "clockwise", "counterclockwise"]],
    steps: int,
    mode: Literal["linear", "hsv", "oklch"] = "linear",
) -> tuple[hexa, ...]:
    """Generate a multi-color gradient with optional directional hue rotation.\n
    ----------------------------------------------------------------------------------------------------
    - `colors` – List of colors to interpolate between.
    - `directions` – List of hue directions for each segment (length = `len(colors) - 1`).
    - `steps` – Total number of gradient steps across all segments.
    - `mode` – Linear (RGB), HSV, or OKLCH interpolation mode."""

    if len(colors) < 2:
        raise ValueError("Need at least 2 colors for a gradient")
    if len(directions) != len(colors) - 1:
        raise ValueError(f"Need {len(colors) - 1} directions for {len(colors)} colors")

    num_segments = len(colors) - 1

    # We want `steps` total colors in the final gradient.
    # When joining segments, we skip first color of each non-first segment.
    # So: `total_colors = seg1_colors + seg2_colors - 1 + seg3_colors - 1 + ...`
    # Which means: `steps = sum(segment_steps) - (num_segments - 1)`
    # Therefore: `sum(segment_steps) = steps + (num_segments - 1)`

    total_segment_steps = steps + (num_segments - 1)
    steps_per_segment = total_segment_steps // num_segments
    remainder = total_segment_steps % num_segments

    gradient: list[hexa] = []

    for seg_idx in range(num_segments):
        segment = generate_gradient(
            color_1=colors[seg_idx],
            color_2=colors[seg_idx + 1],
            steps=steps_per_segment + (1 if seg_idx < remainder else 0),  # Distribute remainder steps across first segments.
            mode=mode,
            hue_direction=directions[seg_idx],
        )

        if seg_idx == 0:
            gradient.extend(segment)
        else:
            gradient.extend(segment[1:])  # Skip first color to avoid duplication.

    return tuple(gradient)


def generate_gradient(
    color_1: rgba,
    color_2: rgba,
    steps: int,
    mode: Literal["linear", "hsv", "oklch"] = "linear",
    hue_direction: Literal["shortest", "clockwise", "counterclockwise"] = "shortest",
) -> tuple[hexa, ...]:
    """Generate and display a color gradient.\n
    ----------------------------------------------------------------------------------------------------
    - `color_1` – Starting hex color.
    - `color_2` – Ending hex color.
    - `steps` – Number of gradient steps (total across all segments).
    - `mode` – Linear (RGB), HSV, or OKLCH interpolation mode.
    - `hue_direction` – Direction for hue interpolation (only relevant for OKLCH and HSV modes)."""

    gradient: list[hexa] = []

    if mode == "oklch":
        # OKLCH interpolation for perceptual uniformity:
        for i in range(steps):
            t = i / (steps - 1) if steps > 1 else 0
            rgb = interpolate_oklch(color_1, color_2, t, hue_direction)
            gradient.append(rgb.as_hexa())

    elif mode == "hsv":
        # HSV interpolation (allows hue rotation):
        for i in range(steps):
            t = i / (steps - 1) if steps > 1 else 0
            rgb = interpolate_hsv(color_1, color_2, t, hue_direction)
            gradient.append(rgb.as_hexa())

    else:
        # Linear RGB interpolation:
        for i in range(steps):
            t = i / (steps - 1) if steps > 1 else 0
            r = round(color_1[0] + (color_2[0] - color_1[0]) * t)
            g = round(color_1[1] + (color_2[1] - color_1[1]) * t)
            b = round(color_1[2] + (color_2[2] - color_1[2]) * t)
            gradient.append(rgba(r, g, b).as_hexa())

    return tuple(gradient)


def display_gradient(
    gradient: tuple[hexa, ...],
    source_colors: list[hexa],
    width: int,
    list_colors: bool = False,
    numerate: bool = False,
) -> None:
    """Display gradient using half-block char to fit 2 colors per character position.\n
    ----------------------------------------------------------------------------------------------------
    - `gradient` – Tuple of gradient colors to display.
    - `width` – Terminal width for display.
    - `list_colors` – Whether to show the color list.
    - `numerate` – Whether to show step numbers.
    - `source_colors` – Original input colors (for multi-color gradient summary)."""

    # Each `▌` shows 2 colors (FG + BG), so we fill `total_width` positions.
    # We need to map `total_colors` across `total_width * 2` half-positions:
    gradient_parts: list[RenderSegment] = []
    total_colors = len(gradient)

    for i in range(width):
        # Map character position to gradient color indices.
        # Left half (FG) and right half (BG) of this character:
        left_pos = (i * 2) * total_colors / (width * 2)
        right_pos = (i * 2 + 1) * total_colors / (width * 2)

        left_idx = min(int(left_pos), total_colors - 1)
        right_idx = min(int(right_pos), total_colors - 1)

        fg_color = gradient[left_idx]
        bg_color = gradient[right_idx]

        gradient_parts.append((S.hex(fg_color) | S.BG.hex(bg_color))("▌"))

    gradient_str = S(*gradient_parts, "\n").ansi * 4

    color_segments = [(S.BOLD | S.BG.hex(color).as_text_fg() | S.BG.hex(color))(f" {color} ") for color in source_colors]
    summary = S(
        S.BG.BLACK(" "),
        (S.DIM | S.WHITE | S.BG.BLACK)("›").join(color_segments),  # ruff:ignore[ambiguous-unicode-character-string]
        (S.WHITE | S.BG.BLACK)(" in ", S.BOLD(str(total_colors)), " steps "),
    )
    summary = S(S.BLACK("▄" * len(summary)), summary, S.BLACK("▀" * len(summary)), sep="\n")

    if not list_colors:
        print(f"\n{gradient_str}\n{summary}")
        return

    if numerate:
        num_width = len(str(len(gradient)))
        color_list = "\n".join(
            S(
                " ",
                S.ITALIC,
                (S.DIM | S.WHITE)(f"{i:>{num_width}}  "),
                (S.BOLD | S.BG.hex(color).as_text_fg() | S.BG.hex(color))(f" {color} "),
            ).ansi
            for i, color in enumerate(gradient, 1)
        )
    else:
        color_list = "\n".join(
            (S.BOLD | S.ITALIC | S.BG.hex(color).as_text_fg() | S.BG.hex(color))(f" {color} ").ansi for color in gradient
        )

    print(f"\n{gradient_str}\n{summary}\n\n{color_list}")


def parse_color_args(
    color_args: list[str],
    mode: Literal["linear", "hsv", "oklch"] = "linear",
) -> tuple[
    list[rgba],
    list[Literal["shortest", "clockwise", "counterclockwise"]],
]:
    """Parse color arguments and extract colors and directions.\n
    ----------------------------------------------------------------------------------------------------
    - `color_args` – List of color arguments (hex colors and optional direction arrows).
    - `mode` – Interpolation mode (linear, hsv, oklch)."""

    directions: list[Literal["shortest", "clockwise", "counterclockwise"]] = []
    colors: list[rgba] = []

    i = 0
    while i < len(color_args):
        arg = str(color_args[i])

        # Check if it's a direction arrow:
        if arg in (">", "<"):
            if mode == "linear":
                raise ValueError(
                    S(
                        "Direction arrows (",
                        S.BR.CYAN("< >"),
                        ") are only supported with ",
                        S.BR.BLUE("--hsv"),
                        " or ",
                        S.BR.BLUE("--oklch"),
                        " modes",
                    )
                )

            if len(colors) == 0:
                raise ValueError(f"Direction arrow '{arg}' cannot appear before the first color")

            # Add direction for previous segment:
            if arg == ">":
                directions.append("clockwise")
            elif arg == "<":
                directions.append("counterclockwise")
            else:
                directions.append("shortest")
            i += 1

        else:
            # It's a color:
            try:
                if (hex_color := hexa(arg)).has_alpha():
                    raise ValueError(S("Color ", S.BR.CYAN(arg), " includes alpha channel, which is not supported"))
                colors.append(hex_color.as_rgba())

            except Exception as exc:
                raise ValueError(
                    S(
                        ("Invalid color format ", S.BR.CYAN(arg), ":"),
                        ("Expected opaque hex color (e.g., ", S.BR.CYAN("F00"), " or ", S.BR.CYAN("FF0000"), ")"),
                        sep="\n",
                    )
                ) from exc

            # If this isn't the first color and we don't have a direction yet for this segment:
            if len(colors) > 1 and len(directions) < len(colors) - 1:
                directions.append("shortest")

            i += 1

    return colors, directions


def main() -> None:
    # Determine interpolation mode:
    if ARGS.hsv.exists and ARGS.oklch.exists:
        raise ValueError(S("Cannot use both ", S.BR.BLUE("--hsv"), " and ", S.BR.BLUE("--oklch"), " options together"))

    mode = "hsv" if ARGS.hsv.exists else "oklch" if ARGS.oklch.exists else "linear"
    color_args = " ".join(ARGS.color_points.vals()).split()

    if len(color_args) < 2:
        raise ValueError(S("Please provide at least 2 colors in hex format (e.g., ", S.BR.CYAN("F00 00F"), ")"))

    # Parse colors and directions:
    colors, directions = parse_color_args(color_args, mode)

    # Validate we have at least 2 colors:
    if len(colors) < 2:
        raise ValueError("Please provide at least 2 colors")

    # Ensure we have directions for all segments:
    while len(directions) < len(colors) - 1:
        directions.append("shortest")

    if (sv := ARGS.steps.val(int, default=None)) and sv <= 1:
        raise ValueError("Steps must be a positive integer, bigger than 1")

    total_steps = sv if sv is not None else xx.console.get_width() * 2

    gradient = generate_multi_gradient(colors=colors, directions=directions, steps=total_steps, mode=mode)
    display_gradient(
        gradient=gradient,
        source_colors=[color.as_hexa() for color in colors],
        width=xx.console.get_width(),
        list_colors=bool(ARGS.list or ARGS.numerate),
        numerate=ARGS.numerate.exists,
    )

    print()


if __name__ == "__main__":
    args = ArgumentParser(
        title="Gradient",
        subtitle="Generate and preview advanced color gradients",
        examples=[
            ("{cmd} F00 00F", "Linear RGB interpolation"),
            ("{cmd} F00 00F 0F0", "Multicolor linear gradient"),
            ("{cmd} F00 00F --steps=5", "5 steps total across segments"),
            ("{cmd} F00 00F 0F0 -O", "OKLCH, shortest hue path"),
            ('{cmd} "F00 > 00F" -H', "HSV, clockwise hue rotation"),
            ('{cmd} "F00 > 00F < 0F0" -H', "HSV, mixed hue directions"),
        ],
        epilog=S(
            (
                S.BOLD("Direction: "),
                S.DIM("(only with ", S.BR.BLUE("--hsv"), " or ", S.BR.BLUE("--oklch"), " modes)"),
            ),
            ("  ", S.BR.CYAN(">"), "                 Rotate hue clockwise"),
            ("  ", S.BR.CYAN("<"), "                 Rotate hue counterclockwise"),
            ("  ", S.DIM("no arrow"), "          Use shortest hue path ", S.DIM("(default)")),
            sep="\n",
        ),
    )

    args.add_arg(
        "color_points",
        nargs="+",
        help=("Hex colors to create gradient between ", S.DIM("(at least 2 required)")),
    )
    args.add_opt(
        {"-s", "--steps"},
        expects_value="N",
        help=("Number of gradient steps ", S.DIM("(total across all color segments)")),
    )
    args.add_opt({"-H", "--hsv"}, help="Use HSV interpolation with hue rotation")
    args.add_opt(
        {"-O", "--oklch"},
        help="Use perceptually uniform OKLCH interpolation with hue rotation",
    )
    args.add_opt({"-l", "--list"}, help="Show list of all gradient colors")
    args.add_opt(
        {"-n", "--numerate"},
        help=("Show step numbers alongside listed colors ", S.DIM("(implies ", S.BR.BLUE("-l"), ")")),
    )

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)

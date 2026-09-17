#!/usr/bin/env python3
# ruff:file-ignore[complex-structure, ambiguous-unicode-character-string]
# x-cmds:file[update]

"""
Do advanced calculations from the command line.
Supports a wide range of mathematical operations, functions and constants.
There's no number size limit — the only limit is your system's memory.
"""

import re
import sys
from collections.abc import Callable, Generator
from contextlib import suppress
from typing import Any, ClassVar
import numpy
import sympy
import xulbux as xx
from xulbux import ArgumentParser, LazyRegex, S
from xulbux.ansi import Renderable

sys.set_int_max_str_digits(0)  # 0 = no limit.

PATTERNS = LazyRegex(thousands_seps=r"(?<=\d)[_'](?=\d)")


def sanitize(expression: Any, /) -> sympy.Expr:
    return sympy.sympify(expression)  # pyright:ignore[reportUnknownMemberType,reportUnknownVariableType]


def clean_num(token: str, /) -> str:
    """Remove underscores from numeric tokens for proper parsing."""
    if (no_seps_num := PATTERNS.thousands_seps.sub("", token)).replace(".", "").replace("-", "").isdigit():
        return no_seps_num
    return token


class OPERATORS:
    # Arithmetic operators:
    MINUS = ("o:minus", ["-", "−"])
    PLUS = ("o:plus", ["+", "＋"])
    MULTIPLY = ("o:multiply", ["*", "×", "∗", "·"])
    DIVIDE = ("o:divide", ["/", "÷"])
    FLOOR_DIVIDE = ("o:floor_divide", ["//", "⌊/⌋"])
    MODULO = ("o:modulo", ["%", "mod"])
    POWER = ("o:power", ["**", "^"])
    # Logic operators:
    AND = ("o:and", ["and", "&&", "∧"])
    OR = ("o:or", ["or", "||", "∨"])
    NOT = ("o:not", ["not", "!", "¬"])
    XOR = ("o:xor", ["xor", "⊻"])
    # Postfix operators:
    FACTORIAL = ("o:factorial", ["!"])
    # Comparison operators:
    EQUALS = ("o:equals", ["eq", "=", "==", "≡"])
    NOT_EQUALS = ("o:not_equals", ["ne", "!=", "≠", "<>"])
    LESS_THAN = ("o:less_than", ["lt", "<", "＜"])
    LESS_THAN_EQUAL = ("o:less_equal_than", ["le", "<=", "≤", "⩽"])
    GREATER_THAN = ("o:greater_than", ["gt", ">", "＞"])
    GREATER_THAN_EQUAL = ("o:greater_equal_than", ["ge", ">=", "≥", "⩾"])

    ALL = (
        MINUS,
        PLUS,
        MULTIPLY,
        DIVIDE,
        FLOOR_DIVIDE,
        MODULO,
        POWER,
        AND,
        OR,
        NOT,
        XOR,
        FACTORIAL,
        EQUALS,
        NOT_EQUALS,
        LESS_THAN,
        LESS_THAN_EQUAL,
        GREATER_THAN,
        GREATER_THAN_EQUAL,
    )
    ALL_TOKENS: tuple[str, ...] = tuple(token for _, tokens in ALL for token in tokens)

    PRECEDENCE: ClassVar[dict[str | tuple[str, ...], int]] = {
        # Higher values represent higher precedence:
        FACTORIAL[0]: 5,
        POWER[0]: 4,
        (MULTIPLY[0], DIVIDE[0], FLOOR_DIVIDE[0], MODULO[0]): 3,
        (PLUS[0], MINUS[0]): 2,
        AND[0]: 1,
        OR[0]: 0,
        (EQUALS[0], NOT_EQUALS[0], LESS_THAN[0], LESS_THAN_EQUAL[0], GREATER_THAN[0], GREATER_THAN_EQUAL[0]): -1,
        NOT[0]: -2,
        XOR[0]: -3,
    }

    IMPLEMENT: ClassVar[dict[str, Callable[[Any, Any], Any]]] = {
        # Arithmetic operators:
        MINUS[0]: lambda a, b: sympy.Add(sanitize(a), sympy.Mul(sanitize(b), sympy.Integer(-1))),
        PLUS[0]: lambda a, b: sympy.Add(sanitize(a), sanitize(b)),
        MULTIPLY[0]: lambda a, b: sympy.Mul(sanitize(a), sanitize(b)),
        DIVIDE[0]: lambda a, b: sympy.Mul(sanitize(a), sympy.Pow(sanitize(b), -1)),
        FLOOR_DIVIDE[0]: lambda a, b: sympy.floor(sympy.Mul(sanitize(a), sympy.Pow(sanitize(b), -1))),
        MODULO[0]: lambda a, b: sympy.Mod(sanitize(a), sanitize(b)),
        POWER[0]: lambda a, b: sympy.Pow(sanitize(a), sanitize(b)),
        # Logic operators:
        AND[0]: lambda a, b: 1 if (bool(a) and bool(b)) else 0,
        OR[0]: lambda a, b: 1 if (bool(a) or bool(b)) else 0,
        NOT[0]: lambda a, _: 1 if not bool(a) else 0,
        XOR[0]: lambda a, b: 1 if ((bool(a) and not bool(b)) or (not bool(a) and bool(b))) else 0,
        # Postfix operators:
        FACTORIAL[0]: lambda a, _: sympy.factorial(sanitize(a)),
        # Comparison operators:
        EQUALS[0]: lambda a, b: 1 if a == b else 0,
        NOT_EQUALS[0]: lambda a, b: 1 if a != b else 0,
        LESS_THAN[0]: lambda a, b: 1 if a < b else 0,
        LESS_THAN_EQUAL[0]: lambda a, b: 1 if a <= b else 0,
        GREATER_THAN[0]: lambda a, b: 1 if a > b else 0,
        GREATER_THAN_EQUAL[0]: lambda a, b: 1 if a >= b else 0,
    }

    @classmethod
    def get(cls, operator_id: str, /) -> Callable[[Any, Any], Any] | None:
        """Get the operator function by operator ID."""
        return cls.IMPLEMENT.get(operator_id)

    @classmethod
    def get_id(cls, token: str, /) -> str | None:
        """Get the operator ID for a token by searching through the token lists."""
        token_lower = token.lower()
        for op_id, symbols in cls.ALL:
            if token_lower in symbols:
                return op_id
        return None

    @classmethod
    def is_operator(cls, token: str, /) -> bool:
        """Check if a token is an operator by searching through the token lists."""
        return cls.get_id(token) is not None

    @classmethod
    def get_precedence(cls, operator_id: str, /) -> int:
        """Get the operator precedence by operator ID."""
        for keys, val in cls.PRECEDENCE.items():
            if isinstance(keys, tuple):
                if operator_id in keys:
                    return val
            else:
                if operator_id == keys:
                    return val
        return 5  # Default


class CONSTANTS:
    # Mathematical constants:
    ANS = ("c:ans", ["ans", "answer"])
    E = ("c:e", ["e", "euler"])
    INF = ("c:inf", ["inf", "infinity", "∞"])
    PI = ("c:pi", ["pi", "π"])
    TAU = ("c:tau", ["tau", "τ"])
    PHI = ("c:phi", ["phi", "φ", "golden"])

    ALL = (ANS, E, INF, PI, TAU, PHI)
    ALL_TOKENS: tuple[str, ...] = tuple(token for _, tokens in ALL for token in tokens)

    IMPLEMENT: ClassVar[dict[str, object]] = {
        ANS[0]: None,
        E[0]: sympy.E,
        INF[0]: sympy.oo,
        PI[0]: sympy.pi,
        TAU[0]: 2 * sympy.pi,
        PHI[0]: sympy.GoldenRatio,
    }

    @classmethod
    def get(cls, constant_id: str, /) -> object | None:
        """Get the constant function by constant ID."""
        return cls.IMPLEMENT.get(constant_id)

    @classmethod
    def get_id(cls, token: str, /) -> str | None:
        """Get the constant ID for a token by searching through the token lists."""
        token_lower = token.lower()
        for const_id, symbols in cls.ALL:
            if token_lower in symbols:
                return const_id
        return None

    @classmethod
    def is_constant(cls, token: str, /) -> bool:
        """Check if a token is a constant by searching through the token lists."""
        return cls.get_id(token) is not None


class FUNCTIONS:
    # Programming functions:
    ABS = ("f:abs", ["abs", "absolute", "magnitude"])
    FLOOR = ("f:floor", ["floor"])
    CEIL = ("f:ceil", ["ceil", "ceiling"])
    ROUND = ("f:round", ["round"])
    SIGN = ("f:sign", ["sign", "sgn"])
    # Logarithmic functions:
    LN = ("f:ln", ["ln", "log_e", "natural_log", "loge"])
    LOG = ("f:log", ["log", "logarithm"])
    LOGB = ("f:logb", ["logb", "log_base"])
    LOG2 = ("f:log2", ["log2", "log_2"])
    LOG10 = ("f:log10", ["log10"])
    EXP = ("f:exp", ["exp", "exponential"])
    # Trigonometric functions:
    RAD = ("f:rad", ["rad", "radians", "to_radians"])
    DEG = ("f:deg", ["deg", "degrees", "to_degrees"])
    SIN = ("f:sin", ["sin", "sine"])
    ASIN = ("f:asin", ["asin", "arcsin", "arcsine", "sin_inv"])
    COS = ("f:cos", ["cos", "cosine"])
    ACOS = ("f:acos", ["acos", "arccos", "arccosine", "cos_inv"])
    TAN = ("f:tan", ["tan", "tangent"])
    ATAN = ("f:atan", ["atan", "arctan", "arctangent", "tan_inv"])
    # Hyperbolic functions:
    SINH = ("f:sinh", ["sinh", "hyperbolic_sine"])
    COSH = ("f:cosh", ["cosh", "hyperbolic_cosine"])
    TANH = ("f:tanh", ["tanh", "hyperbolic_tangent"])
    ASINH = ("f:asinh", ["asinh", "arcsinh", "inverse_sinh"])
    ACOSH = ("f:acosh", ["acosh", "arccosh", "inverse_cosh"])
    ATANH = ("f:atanh", ["atanh", "arctanh", "inverse_tanh"])
    # Additional trigonometric functions:
    COT = ("f:cot", ["cot", "cotangent"])
    SEC = ("f:sec", ["sec", "secant"])
    CSC = ("f:csc", ["csc", "cosecant"])
    # Additional functions:
    FAC = ("f:fac", ["fac", "factorial", "fact"])
    SQRT = ("f:sqrt", ["sqrt", "square_root", "√"])
    CBRT = ("f:cbrt", ["cbrt", "cube_root", "∛"])
    POW = ("f:pow", ["pow", "power"])
    # Statistical functions:
    MIN = ("f:min", ["min", "minimum"])
    MAX = ("f:max", ["max", "maximum"])

    ALL = (
        ABS,
        FLOOR,
        CEIL,
        ROUND,
        SIGN,
        LN,
        LOG,
        LOGB,
        LOG2,
        LOG10,
        EXP,
        RAD,
        DEG,
        SIN,
        ASIN,
        COS,
        ACOS,
        TAN,
        ATAN,
        SINH,
        COSH,
        TANH,
        ASINH,
        ACOSH,
        ATANH,
        COT,
        SEC,
        CSC,
        FAC,
        SQRT,
        CBRT,
        POW,
        MIN,
        MAX,
    )
    ALL_TOKENS: tuple[str, ...] = tuple(token for _, tokens in ALL for token in tokens)

    IMPLEMENT: ClassVar[dict[str, Callable[[Any], Any]]] = {
        # Programming functions:
        ABS[0]: lambda a: abs(sanitize(a)),
        FLOOR[0]: lambda a: sympy.floor(sanitize(a)),
        CEIL[0]: lambda a: sympy.ceiling(sanitize(a)),
        ROUND[0]: lambda a: sympy.floor(sanitize(a) + sympy.Rational(1, 2)),  # pyright:ignore[reportOperatorIssue]
        SIGN[0]: lambda a: sympy.sign(sanitize(a)),
        # Logarithmic functions:
        LN[0]: lambda a: sympy.log(sanitize(a)),
        LOG[0]: lambda a, b=None: sympy.log(sanitize(a), sanitize(b)) if b is not None else sympy.log(sanitize(a), 10),
        LOGB[0]: lambda a, b=None: sympy.log(sanitize(a), sanitize(b)) if b is not None else sympy.log(sanitize(a)),
        LOG2[0]: lambda a: sympy.log(sanitize(a), 2),
        LOG10[0]: lambda a: sympy.log(sanitize(a), 10),
        EXP[0]: lambda a: sympy.exp(sanitize(a)),
        # Trigonometric functions:
        RAD[0]: lambda a: sympy.rad(sanitize(a)),  # pyright:ignore[reportUnknownLambdaType,reportUnknownMemberType]
        DEG[0]: lambda a: sympy.deg(sanitize(a)),  # pyright:ignore[reportUnknownLambdaType,reportUnknownMemberType]
        SIN[0]: lambda a: sympy.sin(sanitize(a)),
        ASIN[0]: lambda a: sympy.asin(sanitize(a)),
        COS[0]: lambda a: sympy.cos(sanitize(a)),
        ACOS[0]: lambda a: sympy.acos(sanitize(a)),
        TAN[0]: lambda a: sympy.tan(sanitize(a)),
        ATAN[0]: lambda a: sympy.atan(sanitize(a)),
        # Hyperbolic functions:
        SINH[0]: lambda a: sympy.sinh(sanitize(a)),
        COSH[0]: lambda a: sympy.cosh(sanitize(a)),
        TANH[0]: lambda a: sympy.tanh(sanitize(a)),
        ASINH[0]: lambda a: sympy.asinh(sanitize(a)),
        ACOSH[0]: lambda a: sympy.acosh(sanitize(a)),
        ATANH[0]: lambda a: sympy.atanh(sanitize(a)),
        # Additional trigonometric functions:
        COT[0]: lambda a: sympy.cot(sanitize(a)),
        SEC[0]: lambda a: sympy.sec(sanitize(a)),
        CSC[0]: lambda a: sympy.csc(sanitize(a)),
        # Additional functions:
        FAC[0]: lambda a: sympy.factorial(sanitize(a)),
        SQRT[0]: lambda a: sympy.sqrt(sanitize(a)),  # pyright:ignore[reportUnknownMemberType]
        CBRT[0]: lambda a: sympy.Pow(sanitize(a), sympy.Rational(1, 3)),
        POW[0]: lambda a, b=None: sympy.Pow(sanitize(a), sanitize(b)) if b is not None else sanitize(a),
        # Statistical functions:
        MIN[0]: lambda a, b=None: sympy.Min(sanitize(a), sanitize(b)) if b is not None else sanitize(a),
        MAX[0]: lambda a, b=None: sympy.Max(sanitize(a), sanitize(b)) if b is not None else sanitize(a),
    }

    @classmethod
    def get(cls, func_id: str, /) -> Callable[[Any], Any] | None:
        """Get the function lambda by function ID."""
        return cls.IMPLEMENT.get(func_id)

    @classmethod
    def get_id(cls, token: str, /) -> str | None:
        """Get the function ID for a token by searching through the token lists."""
        token_lower = token.lower()
        for func_id, symbols in cls.ALL:
            if token_lower in symbols:
                return func_id
        return None

    @classmethod
    def is_function(cls, token: str, /) -> bool:
        """Check if a token is a function by searching through the token lists."""
        return cls.get_id(token) is not None


TOKEN_RX = re.compile(
    "|".join(map(re.escape, sorted(OPERATORS.ALL_TOKENS + CONSTANTS.ALL_TOKENS + FUNCTIONS.ALL_TOKENS, key=len, reverse=True)))
    + r"|[a-z]+|"
    + "|".join(map(re.escape, OPERATORS.MINUS[1]))
    + r"\d+(?:[_']\d+)*\.\d+(?:[_']\d+)*|"
    + "|".join(map(re.escape, OPERATORS.MINUS[1]))
    + r"\d+(?:[_']\d+)*|"
    + r"\d+(?:[_']\d+)*\.\d+(?:[_']\d+)*|\d+(?:[_']\d+)*|"
    + r"\(|\)|,",
    re.IGNORECASE,
)


def print_overwrite(*values: Renderable, sep: str = " ", end: str = "\n") -> None:
    S("\033[2K\r", S(*values, sep=sep)).print(end=end)


def print_line(title: str | None = None, /, *, char: str = "═", width: int = xx.console.get_width(), end: str = "\n") -> None:
    if not title:
        S.DIM(char * width).print(end=end)
        return

    left_len = max(0, (width - len(title) - 2) // 2)
    right_len = max(0, width - len(title) - 2 - left_len)
    S(S.DIM(char * left_len), " ", S.BOLD(title), " ", S.DIM(char * right_len)).print(end=end)


def clear_lines(num_lines: int = 1) -> None:
    for _ in range(num_lines):
        print("\033[F\033[K", end="", flush=True)


class Calc:
    def __init__(self, /, *, calc_str: str, last_ans: str | None = None, precision: int = 110, max_num_len: int = 100) -> None:
        self.calc_str = calc_str
        self.last_ans = last_ans
        self.precision = precision
        self.max_num_len = max_num_len
        self.inf_precision = precision == -1

    def __str__(self) -> str:
        return self.calc_str

    def __repr__(self) -> str:
        return (
            f"Calc(calc_str={self.calc_str!r}, last_ans={self.last_ans!r}, "
            f"precision={self.precision}, max_num_len={self.max_num_len})"
        )

    def eval(self) -> str:
        if DEBUG:
            clear_lines()
            print()
            print_line("NEW CALCULATION")
            S(S.DIM("raw calculation string:\n"), (S.BOLD | S.DIM)(">>>"), f" {self.calc_str}").print()
        else:
            print_overwrite((S.DIM | S.WHITE)("calculating..."), end="")

        # Skip precision adjustments for infinite precision (-1):
        if not self.inf_precision and self.precision <= self.max_num_len:
            self.max_num_len = self.precision
            self.precision += 10
        norm_calc_str = re.sub(r"\s+", "", self.calc_str.strip())

        if DEBUG:
            S(S.DIM("normalized calculation string:\n"), (S.BOLD | S.DIM)(">>>"), f" {norm_calc_str}").print()
            S(S.DIM("precision:"), f" {self.precision}").print()
            S(S.DIM("max number length:"), f" {self.max_num_len}").print()

        self.last_ans = self._perform_eval(norm_calc_str)
        return self.format_readability(self.last_ans)

    def format_result(self, result: object, /) -> str:
        if DEBUG:
            print_line("FORMAT RESULT")
            S(S.DIM("result:"), f" {result}").print()
            S(S.DIM("precision:"), f" {self.precision} ", S.DIM("(infinite: "), str(self.inf_precision), S.DIM(")")).print()

        # For infinite precision, just convert to string without formatting:
        if self.inf_precision:
            result_str = str(result)
            if DEBUG:
                S(S.DIM("infinite precision result:"), f" {result_str}").print()
            return result_str

        # Check if result is an exact integer to avoid float precision errors:
        is_exact_integer = False
        with suppress(Exception):
            if (
                (hasattr(result, "is_integer") and getattr(result, "is_integer", False))
                or isinstance(result, sympy.Integer)
                or (hasattr(result, "is_Integer") and getattr(result, "is_Integer", False))
                or isinstance(result, int)
            ):
                is_exact_integer = True

        if is_exact_integer:
            result_str = str(result)
            if DEBUG:
                S(S.DIM("exact integer result (preserving for formatting):"), f" {result_str}").print()
        else:
            try:
                result_str = "{:.{}f}".format(result, self.precision)
                result_str = result_str.rstrip("0").rstrip(".") if "." in result_str else result_str
            except OverflowError:
                result_str = str(result)
            if DEBUG:
                S(S.DIM("formatted decimal result:"), f" {result_str}").print()

        return result_str

    def format_readability(self, num_str: str, /) -> str:
        if not DEBUG:
            print_overwrite((S.DIM | S.WHITE)("formatting..."), end="")

        # Format with thousands separators if requested:
        if ARGS.format.exists:
            if DEBUG:
                print_line("FORMATTING WITH SEPARATORS")
                S(S.DIM("should format:"), f" {ARGS.format.exists}").print()

            sep = ARGS.format.val(default=",")

            if DEBUG:
                S(S.DIM("separator:"), f" {sep}").print()
                S(S.DIM("input num_str:"), f" {num_str}").print()

            if "." in num_str:
                int_part, decimal_part = num_str.split(".", 1)

                if int_part.lstrip("-").isdigit() and len(int_part.lstrip("-")) > 3:
                    formatted_int = ""
                    sign = "-" if int_part.startswith("-") else ""
                    digits = int_part.lstrip("-")

                    for i, digit in enumerate(reversed(digits)):
                        if i > 0 and i % 3 == 0:
                            formatted_int = sep + formatted_int
                        formatted_int = digit + formatted_int

                    num_str = sign + formatted_int + "." + decimal_part

                    if DEBUG:
                        S(S.DIM("formatted decimal number:"), f" {num_str}").print()

            else:
                if num_str.lstrip("-").isdigit() and len(num_str.lstrip("-")) > 3:
                    formatted_num: str = ""
                    sign: str = "-" if num_str.startswith("-") else ""
                    digits: str = num_str.lstrip("-")

                    for i, digit in enumerate(reversed(digits)):
                        if i > 0 and i % 3 == 0:
                            formatted_num = sep + formatted_num
                        formatted_num = digit + formatted_num

                    num_str = sign + formatted_num

                    if DEBUG:
                        S(S.DIM("formatted whole number:"), f" {num_str}").print()

        # Truncate repeating decimal (skip for infinite precision):
        if not self.inf_precision and len(num_str) > self.max_num_len and "." in num_str:
            num_str = num_str[:-10]
            int_part, decimal_part = num_str.split(".")
            short_decimal_part = decimal_part[: self.max_num_len]

            if DEBUG:
                print_line("TRUNCATING REPEATING DECIMAL")
                S(S.DIM("input string:"), f" {num_str}").print()
                S(S.DIM("decimal part:"), f" {short_decimal_part}").print()

            if self._is_recurring(short_decimal_part):
                num_str = f"{int_part}.{short_decimal_part}…"
            else:
                num_str = f"{int_part}.{short_decimal_part}"
            if DEBUG:
                S(S.DIM("formatted string:"), f" {num_str}").print()

        # Format long numbers to exponents (skip for infinite precision):
        elif not self.inf_precision and len(num_str) > self.max_num_len:
            if DEBUG:
                print_line("FORMATTING LONG NUMBERS TO EXPONENTS")
                S(S.DIM("input string:"), f" {num_str}").print()
            num_str = self._format_exponents(num_str)
            if DEBUG:
                S(S.DIM("formatted string:"), f" {num_str}").print()

        return num_str

    def _format_exponents(self, string: str, /) -> str:
        pattern = re.compile(r"(\d*\.\d+|\d+)(?![\de])")

        def replace_match(match: re.Match[str]) -> str:
            if len(str(number_sequence := match.group(1))) <= self.max_num_len:
                return number_sequence

            base = number_sequence[: self.max_num_len]
            exponent_value = len(number_sequence) - self.max_num_len

            sign = "+" if exponent_value >= 0 else "-"

            return base + "e" + sign + str(abs(exponent_value))

        return pattern.sub(replace_match, string)

    def _is_recurring(self, string: str, /, *, max_check_loops: int = -1) -> list[bool] | bool:
        if not (repts := list(self._get_rept(string))):
            return False

        repts.reverse()
        loops = len(repts) if max_check_loops < 0 or len(repts) < max_check_loops else max_check_loops

        for loop in range(loops):
            rept = repts[loop]

            if string[-(len(rept) * 2) :] != rept * 2:
                found = i = 0

                for i in range(len(string), 1, -1):
                    if string[i - len(rept) : i] == rept:
                        if found > 0:
                            break
                        else:
                            found += 1

                if not found:
                    return False

                else:
                    rept_i = 0

                    for char in string[i:]:
                        if char == rept[rept_i]:
                            i += 1
                        else:
                            i = 0
                            break
                        rept_i += 1
                        if rept_i == len(rept):
                            rept_i = 0

                    if i > 0:
                        return True
                    elif loop == loops - 1:
                        return False

            else:
                return True

        return False

    @staticmethod
    def _get_rept(string: str, /) -> Generator[str, None, None]:
        for match in re.finditer(r"(.+?)\1+", string):
            yield match.group(1)

    def _convert_ids_to_symbols(self, tokens: list[str | object], /) -> str:
        """Convert operator/constant/function IDs back to symbols for sympy evaluation."""
        result: list[str] = []

        for token in tokens:
            if isinstance(token, str):
                if token.startswith("o:"):
                    for op_id, symbols in OPERATORS.ALL:
                        if op_id == token:
                            result.append(symbols[0])
                            break
                    else:
                        result.append(token)

                elif token.startswith("c:"):
                    for const_id, symbols in CONSTANTS.ALL:
                        if const_id == token:
                            result.append(symbols[0])
                            break
                    else:
                        result.append(token)

                elif token.startswith("f:"):
                    for func_id, symbols in FUNCTIONS.ALL:
                        if func_id == token:
                            result.append(symbols[0])
                            break
                    else:
                        result.append(token)

                else:
                    result.append(token)

            else:
                result.append(str(token))

        return "".join(result)

    def _find_matches(self, text: str, /) -> list[str | object]:
        preliminary_matches = [match for match in TOKEN_RX.findall(text) if match]  # Filter out empty strings.
        matches: list[str | object] = []
        i = 0

        while i < len(preliminary_matches):
            match = preliminary_matches[i]

            # Check if this is a minus sign that should be combined with the next number:
            if (
                match in OPERATORS.MINUS[1]
                and i + 1 < len(preliminary_matches)
                and PATTERNS.thousands_seps.sub("", preliminary_matches[i + 1]).replace(".", "").isdigit()
            ):
                # Check if this should be treated as a negative number (not subtraction):
                should_be_negative = False
                if i == 0:  # At the beginning.
                    should_be_negative = True
                else:
                    prev_match = preliminary_matches[i - 1]
                    # If previous token is an operator or open parenthesis, treat as negative number:
                    if OPERATORS.is_operator(prev_match) or prev_match == "(" or FUNCTIONS.is_function(prev_match):
                        should_be_negative = True

                if should_be_negative:
                    # Combine minus with next number and clean underscores:
                    matches.append(clean_num(match + preliminary_matches[i + 1]))
                    i += 2  # Skip the next token since we consumed it.
                else:
                    # Keep as separate subtraction operator:
                    matches.append(match)
                    i += 1

            # Distinguish between 'factorial' and 'not':
            elif match == "!":
                should_be_factorial = False

                if i > 0:
                    prev_match = preliminary_matches[i - 1]
                    # If previous token is a number, closing parenthesis, or constant, treat as factorial:
                    if (
                        PATTERNS.thousands_seps.sub("", prev_match).replace(".", "").replace("-", "").isdigit()
                        or prev_match == ")"
                        or CONSTANTS.is_constant(prev_match)
                    ):
                        should_be_factorial = True

                if should_be_factorial:
                    matches.append(OPERATORS.FACTORIAL[0])
                else:
                    matches.append(OPERATORS.NOT[0])

                i += 1

            else:
                # Convert tokens to IDs for operators, constants, and functions:
                if OPERATORS.is_operator(match):
                    matches.append(OPERATORS.get_id(match))
                elif CONSTANTS.is_constant(match):
                    matches.append(CONSTANTS.get_id(match))
                elif FUNCTIONS.is_function(match):
                    matches.append(FUNCTIONS.get_id(match))
                else:
                    # Clean underscores from numeric tokens:
                    matches.append(clean_num(match))

                i += 1

        if DEBUG:
            print_line("FINDING MATCHES")
            S(S.DIM("input text:\n"), (S.BOLD | S.DIM)(">>>"), f" {text}").print()
            S(S.DIM("preliminary matches:"), f" {preliminary_matches}").print()
            S(S.DIM("final matches:"), f" {matches}").print()

        return matches

    def _perform_eval(self, calc_str: str, /) -> str:
        """Internal recursive calculation function that doesn't do preprocessing."""
        SAVE_CALC_STR = calc_str

        # Handle mathematical grouping parentheses (not function calls):
        while "(" in calc_str and ")" in calc_str:
            paren_stack: list[int] = []
            start_idx = -1
            end_idx = -1

            # Find the innermost parentheses:
            for i, char in enumerate(calc_str):
                if char == "(":
                    paren_stack.append(i)

                elif char == ")" and paren_stack:
                    start_idx = paren_stack.pop()
                    end_idx = i

                    # Check if this is a function call by looking at what's before the opening parenthesis:
                    if start_idx > 0:
                        token_start = start_idx - 1
                        while token_start > 0 and calc_str[token_start - 1].isalnum():
                            token_start -= 1
                        token_before = calc_str[token_start:start_idx]

                        # If it's a function, don't process these parentheses:
                        if FUNCTIONS.is_function(token_before):
                            continue

                    inner_expr = calc_str[start_idx + 1 : end_idx]
                    result = self._perform_eval(inner_expr)
                    should_add_mult = start_idx > 0 and calc_str[start_idx - 1].isdigit()
                    calc_str = calc_str[:start_idx] + ("*" if should_add_mult else "") + result + calc_str[end_idx + 1 :]
                    break

            else:
                break

        numpy.set_printoptions(floatmode="fixed", formatter={"float_kind": "{:f}".format})  # Handle scientific notation.
        split = self._find_matches(calc_str)

        # Convert all operands to SymPy expressions:
        def sympify(split_matches: list[str | object], /) -> list[str | object]:
            split_sympy: list[str | object] = []

            for token in split_matches:
                if isinstance(token, str) and token.startswith(("o:", "c:", "f:")):
                    split_sympy.append(token)
                else:
                    try:
                        split_sympy.append(sanitize(token))
                    except Exception:
                        split_sympy.append(token)

            return split_sympy

        split_sympy = sympify(split)

        # Iterate over constants first:
        for c_id, _ in CONSTANTS.ALL:
            while c_id in split:
                idx = split.index(c_id)

                if DEBUG:
                    print_line("CALCULATING CONSTANT")
                    S(S.DIM("constant ID:"), f" {c_id}").print()

                constant_value = (
                    sanitize(self.last_ans)
                    if (c_id == CONSTANTS.ANS[0] and self.last_ans is not None)
                    else CONSTANTS.get(c_id)
                )

                if c_id == CONSTANTS.ANS[0] and constant_value is None:
                    raise Exception("Answer constant was not specified")
                if DEBUG:
                    S(S.DIM("value:"), f" {constant_value}").print()

                formatted_result = str(self.format_result(constant_value))
                new_split: list[str | object] = [*split[:idx], formatted_result, *split[idx + 1 :]]
                split: list[str | object] = new_split
                split_sympy: list[str | object] = sympify(split)

        # Iterate over functions available:
        for f_id, _ in FUNCTIONS.ALL:
            while f_id in split:
                idx = split.index(f_id)

                if idx + 1 < len(split) and split[idx + 1] == "(":
                    paren_count = 0
                    end_paren_idx = -1

                    for i in range(idx + 1, len(split)):
                        if split[i] == "(":
                            paren_count += 1
                        elif split[i] == ")":
                            paren_count -= 1
                            if paren_count == 0:
                                end_paren_idx = i
                                break

                    if end_paren_idx == -1:
                        break
                    arg_tokens = split[idx + 2 : end_paren_idx]

                    if DEBUG:
                        print_line("CALCULATING FUNCTION")
                        S(S.DIM("function ID:"), f" {f_id}").print()
                        S(S.DIM("arg_tokens:"), f" {arg_tokens}").print()

                    # Handle multi-argument functions:
                    if len(arg_tokens) == 1:
                        arg_value = split_sympy[idx + 2]
                        function_impl = FUNCTIONS.get(f_id)
                        if function_impl is None:
                            break
                        result = function_impl(arg_value)

                    else:
                        if "," in arg_tokens:
                            comma_idx = arg_tokens.index(",")
                            arg1_tokens = arg_tokens[:comma_idx]
                            arg2_tokens = arg_tokens[comma_idx + 1 :]

                            if len(arg1_tokens) == 1:
                                arg1_sympy_idx = idx + 2
                                arg1_value = split_sympy[arg1_sympy_idx]
                            else:
                                arg1_str = self._convert_ids_to_symbols(arg1_tokens)
                                arg1_value = sanitize(arg1_str)

                            if len(arg2_tokens) == 1:
                                arg2_sympy_idx = idx + 2 + len(arg1_tokens) + 1
                                arg2_value = split_sympy[arg2_sympy_idx]
                            else:
                                arg2_str = self._convert_ids_to_symbols(arg2_tokens)
                                arg2_value = sanitize(arg2_str)

                            function_impl = FUNCTIONS.get(f_id)
                            if function_impl is None:
                                break

                            if DEBUG:
                                S.DIM("two-argument function").print()
                                S(S.DIM("arg1:"), f" {arg1_value}").print()
                                S(S.DIM("arg2:"), f" {arg2_value}").print()

                            result = function_impl(arg1_value, arg2_value)  # pyright:ignore[reportCallIssue,reportUnknownVariableType]

                        # Single complex argument:
                        else:
                            arg_str = self._convert_ids_to_symbols(arg_tokens)
                            if DEBUG:
                                S(S.DIM("evaluating arg expression:"), f" {arg_str}").print()
                            arg_value = sanitize(arg_str)
                            function_impl = FUNCTIONS.get(f_id)
                            if function_impl is None:
                                break
                            result = function_impl(arg_value)

                    if DEBUG:
                        S(S.DIM("result:"), f" {result}").print()
                    formatted_result = self.format_result(result)  # pyright:ignore[reportUnknownArgumentType]
                    new_split = [*split[:idx], formatted_result, *split[end_paren_idx + 1 :]]
                    split = new_split
                    split_sympy = sympify(split)

                # No parentheses found; not a function call:
                else:
                    break

        # Iterate over operators based on precedence:
        while len(split) > 1:
            operator_positions: list[tuple[int, str, int]] = []
            for i, token in enumerate(split):
                if isinstance(token, str) and token.startswith("o:"):
                    precedence = OPERATORS.get_precedence(token)
                    # Give prefix 'not' higher precedence than binary operators:
                    if token == OPERATORS.NOT[0] and (
                        i == 0 or (isinstance(s := split[i - 1], str) and s.startswith("o:")) or s in {"("}
                    ):
                        precedence = 3  # Higher than binary arithmetic operators.
                    operator_positions.append((i, token, precedence))

            if not operator_positions:
                break

            highest_precedence = max(op[2] for op in operator_positions)
            highest_ops = [op for op in operator_positions if op[2] == highest_precedence]
            idx, operator_id, _ = highest_ops[-1]

            if DEBUG:
                print_line("CALCULATING OPERATOR")
                S(S.DIM("operator ID:"), f" {operator_id}").print()

            operator_func = OPERATORS.get(operator_id)
            if operator_func is None:
                break

            # Postfix factorial operator:
            if operator_id == OPERATORS.FACTORIAL[0]:
                if idx == 0:
                    break
                result = operator_func(split_sympy[idx - 1], None)
                if DEBUG:
                    S(S.DIM("argument:"), f" {split_sympy[idx - 1]}").print()
                    S(S.DIM("operator:"), f" {operator_id} ", S.DIM("(postfix factorial)")).print()
                    S(S.DIM("result:"), f" {result}").print()
                new_split = [*split[: idx - 1], self.format_result(result), *split[idx + 1 :]]

            # Unary minus:
            elif operator_id == OPERATORS.MINUS[0] and (
                idx == 0 or (isinstance(s := split[idx - 1], str) and s.startswith("o:"))
            ):
                if idx + 1 >= len(split):
                    break
                result = operator_func(0, split_sympy[idx + 1])
                if DEBUG:
                    S(S.DIM("argument:"), " 0").print()
                    S(S.DIM("operator:"), f" {operator_id} ", S.DIM("(unary minus)")).print()
                    S(S.DIM("argument:"), f" {split_sympy[idx + 1]}").print()
                    S(S.DIM("result:"), f" {result}").print()
                new_split = [*split[:idx], self.format_result(result), *split[idx + 2 :]]

            # Prefix not operator:
            elif operator_id == OPERATORS.NOT[0] and (
                idx == 0 or (isinstance(s := split[idx - 1], str) and s.startswith("o:")) or s in {"("}
            ):
                if idx + 1 >= len(split):
                    break
                result = operator_func(split_sympy[idx + 1], None)
                if DEBUG:
                    S(S.DIM("operator:"), f" {operator_id} ", S.DIM("(prefix NOT)")).print()
                    S(S.DIM("argument:"), f" {split_sympy[idx + 1]}").print()
                    S(S.DIM("result:"), f" {result}").print()
                new_split = [*split[:idx], self.format_result(result), *split[idx + 2 :]]

            # Binary operator:
            else:
                if idx == 0 or idx + 1 >= len(split):
                    break
                result = operator_func(split_sympy[idx - 1], split_sympy[idx + 1])
                if DEBUG:
                    S(S.DIM("argument:"), f" {split_sympy[idx - 1]}").print()
                    S(S.DIM("operator:"), f" {operator_id}").print()
                    S(S.DIM("argument:"), f" {split_sympy[idx + 1]}").print()
                    S(S.DIM("result:"), f" {result}").print()
                new_split = [*split[: idx - 1], self.format_result(result), *split[idx + 2 :]]

            split = new_split
            split_sympy = sympify(split)

        if len(split) == 1:
            calc_str = str(split[0])
        else:
            calc_str = " ".join([str(s) for s in split])
            try:
                result = sanitize(calc_str)
                calc_str = self.format_result(result)
            except Exception as exc:
                raise Exception(S("Could not perform calculation on ", S.BR.CYAN(SAVE_CALC_STR))) from exc

        if calc_str == SAVE_CALC_STR:
            try:
                sanitize(calc_str)
            except Exception as exc:
                raise Exception(S("Could not perform calculation on ", S.BR.CYAN(SAVE_CALC_STR))) from exc

        return calc_str


def main() -> None:
    print()

    calc_str_parts = ARGS.calculation.vals()
    precision_value = ARGS.precision.val(int, default=100)
    if precision_value <= 0 and precision_value != -1:
        xx.console.fail(
            (
                S.BOLD("ValueError: "),
                "Precision must be positive or ",
                S.BR.CYAN("-1"),
                " for infinite precision, got ",
                S.BR.CYAN(str(precision_value)),
            ),
            end="\n\n",
            exit_code=1,
        )
        return

    if precision_value == -1:
        precision = -1
        max_num_len = -1
    else:
        precision = precision_value + 10
        max_num_len = precision_value

    calculation = Calc(
        calc_str=" ".join([str(v) for v in calc_str_parts]),
        last_ans=ARGS.ans.val(),
        precision=precision,
        max_num_len=max_num_len,
    )
    result = calculation.eval()

    if DEBUG:
        print_line("FINAL RESULT")
        S(S.DIM("answer:"), f" {result}").print()
        print_line()
        print()
    else:
        print_overwrite((S.DIM | S.BR.GREEN | S.BOLD)("="), S.BR.GREEN(result), end="\n\n")


if __name__ == "__main__":
    o_list = S("\n").join([
        S((S.ITALIC | S.DIM)(f"{o_id.split(':')[1]:<22}"), S.DIM(", ").join(symbols)) for o_id, symbols in OPERATORS.ALL
    ])
    c_list = S("\n").join([
        S((S.ITALIC | S.DIM)(f"{c_id.split(':')[1]:<22}"), S.DIM(", ").join(symbols))
        for c_id, symbols in sorted(CONSTANTS.ALL)
    ])
    f_list = S("\n").join([
        S((S.ITALIC | S.DIM)(f"{f_id.split(':')[1]:<22}"), S.DIM(", ").join(symbols))
        for f_id, symbols in sorted(FUNCTIONS.ALL)
    ])

    args = ArgumentParser(
        title="Advanced Calculator",
        subtitle="Perform complex calculations directly from the command line",
        examples=[
            ('{cmd} "2 + 2 * 2"', "Simple arithmetic"),
            ('{cmd} "ans * 2" --ans=6', "Using the 'ans' constant"),
            ('{cmd} "sqrt(ln(10) + 1) / cos(π / 4)" -p=1000', "High precision with functions and constants"),
        ],
        epilog=S(
            S.BOLD("Possible operators:"),
            o_list,
            "",
            S.BOLD("Possible constants:"),
            c_list,
            "",
            S.BOLD("Possible functions:"),
            f_list,
            sep="\n",
        ),
    )

    args.add_arg("calculation", nargs="+", help="The calculation string to evaluate")
    args.add_opt({"-a", "--ans"}, expects_value="VAL", help="Value to use for 'ans' constant")
    args.add_opt(
        {"-p", "--precision"},
        expects_value="N",
        help=("Number of decimal places to calculate ", S.DIM("(default: 100, -1 for infinite)")),
    )
    args.add_opt({"-f", "--format"}, help="Format the output with thousands separators")
    args.add_opt({"-d", "--debug"}, help="Show debug information during calculation")

    global ARGS, DEBUG
    ARGS = args.parse()
    DEBUG = ARGS.debug.exists

    try:
        main()
    except KeyboardInterrupt:
        print_overwrite((S.BOLD | S.BR.RED)("✗"), end="\n\n")
    except RecursionError:
        xx.console.fail(
            (
                S.BOLD("RecursionError: "),
                "Maximum recursion depth exceeded ",
                S.DIM("(possible infinite loop in calculation)"),
            ),
            start="\n\n",
            end="\n\n",
            exit_code=1,
        )
    except MemoryError:
        xx.console.fail(
            (S.BOLD("MemoryError: "), "The operation ran out of memory"),
            start="\n\n",
            end="\n\n",
            exit_code=1,
        )
    except OverflowError as exc:
        xx.console.fail(
            (S.BOLD("OverflowError: "), exc),
            start="\n\n",
            end="\n\n",
            exit_code=1,
        )
    except Exception as exc:
        xx.console.fail(exc, start="\n\n", end="\n\n", exit_code=1)

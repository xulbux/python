---
name: check
description: Strict guidelines and commands for running formatters, linters, type checkers, and resolving all code quality issues.
---

# check

Use this skill to format, lint, type check, and validate code in this repository. All code must pass all checks with zero errors and zero warnings.

---

## 1. Validation Policy

Follow `AGENTS.md` Section 2 for the mandatory validation and testing policy after any edits across the repository. Never assume code is correct without running the checks.

---

## 2. Running Formatters, Linters & Type Checkers

### On Unix (Linux / macOS)

CD into the project root, activate `.venv`, and run:

```bash
ruff format . && ruff check . --fix && pyright
```

### On Windows

CD into the project root and run:

```powershell
ruff format . ; if ($?) { ruff check . --fix } ; if ($?) { pyright }
```

---

## 3. Resolving Errors & Fixing Bugs

-   **Zero Issues Policy:** Every edit session must end with 0 errors, 0 warnings, and 0 lint issues.
-   **Fix Real Bugs in Code:** If a check fails due to an issue or typing mismatch, **fix the code**. Do not suppress or work around real bugs.
-   **Type Ignore Pragmas:** Follow the strict typing and ignore rules in `AGENTS.md` Section 1.

---

## 4. Cross-Platform Reliability (Windows & Unix)

All code must be reliable across platforms without platform-dependent crashes:

1.  **Safely Guard Windows-Only Modules (`ctypes.windll`, `msvcrt`, `winreg`):**
    *   On Linux/macOS, `ctypes` has no `windll` attribute, and `msvcrt` and `winreg` do not exist.
    *   Always place imports for OS-specific libraries inside platform-specific branches (`if sys.platform == "win32":`).
2.  **`pathlib.Path` on Unix:**
    *   Python 3.14+ prevents instantiating `WindowsPath` on POSIX systems.
    *   Do NOT instantiate Windows paths or monkeypatch `sys.platform == "win32"` when running on POSIX systems.
3.  **Cover Both Platform Branches:**
    *   Ensure both Windows (`nt`, `win32`, drive letters) and POSIX (`posix`, `linux`, `darwin`, root slashes) paths and behaviors are properly handled.

---

## 5. Coding Standards & Best Practices

All code across the repository must strictly comply with the core coding standards and idioms defined in `AGENTS.md` (Section 1 for strict typing, Section 4 for performance and Python idioms, and Section 5 for code structure and naming conventions).

#!/usr/bin/env python
"""Flet API compatibility checker — static + dynamic analysis.

Parses all Flet UI source files using the ``ast`` module, then validates
every ``ft.ClassName(kwarg=...)`` constructor call and every
``ft.Namespace.ATTR`` attribute access against the **actually installed**
Flet package (via ``inspect.signature`` / ``hasattr``).

Run::

    python tools/check_flet_api.py          # default: check src/ui/** + main.py
    python tools/check_flet_api.py --fix    # (future) auto-fix mode
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make sure the project root is on sys.path so we can import flet
# from the project venv even if the script is run from a different cwd.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import flet as ft  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
UI_FILES: list[str] = [
    "src/ui/app.py",
    "src/ui/pages/scripts.py",
    "src/ui/pages/matrix.py",
    "src/ui/pages/manage.py",
    "src/ui/pages/review.py",
    "src/ui/pages/settings.py",
    "main.py",
]

# Sub-modules that are accessed as ft.<mod>.<Class>(...) — e.g. ft.dropdown.Option
KNOWN_SUBMODULES: dict[str, str] = {
    "dropdown": "flet.controls.material.dropdown",
    "colors": "flet.controls.colors",
}

# Known deprecated call patterns  (regex applied to source text)
DEPRECATED_PATTERNS: list[tuple[str, str]] = [
    (r"\bft\.app\s*\(", "ft.app() is deprecated since 0.80.0 -- use ft.run()"),
    (r"\bft\.run\s*\(\s*target\s*=", "ft.run(target=...) -- use positional arg: ft.run(main_func)"),
]

# Lowercase helper modules whose methods are deprecated in favor of CamelCase class methods.
# e.g. ft.padding.only() -> ft.Padding.only(),  ft.border.all() -> ft.Border.all()
DEPRECATED_LOWERCASE_HELPERS: dict[str, str] = {
    "padding": "Padding",
    "border": "Border",
    "margin": "Margin",
    "border_radius": "BorderRadius",
}

# Lowercase helper modules that are NOT deprecated (valid sub-namespaces)
VALID_LOWERCASE_MODULES: set[str] = {
    "dropdown",  # ft.dropdown.Option is valid
}

# Controls whose __init__ accepts **kwargs (so signature inspection is blind).
# We list their ACTUAL valid keyword parameters here for explicit checking.
# Generate with: import flet as ft; print([a for a in dir(ft.Tooltip) if not a.startswith('_')])
KWARGS_OVERRIDE: dict[str, set[str]] = {
    "Tooltip": {
        "message",
        "bgcolor",
        "enable_feedback",
        "exclude_from_semantics",
        "exit_duration",
        "margin",
        "mouse_cursor",
        "padding",
        "prefer_below",
        "show_duration",
        "size_constraints",
        "tap_to_dismiss",
        "text_align",
        "text_style",
        "trigger_mode",
        "vertical_offset",
        "wait_duration",
        # common base params
        "key",
        "ref",
        "data",
        "visible",
        "disabled",
        "expand",
        "expand_loose",
        "col",
        "opacity",
        "tooltip",
        "badge",
        "rtl",
        "adaptive",
        "width",
        "height",
        "left",
        "top",
        "right",
        "bottom",
        "align",
        "margin",
        "rotate",
        "scale",
        "offset",
        "flip",
        "transform",
        "aspect_ratio",
    },
}

# Attributes that are dynamic / special and should be ignored in validation
IGNORE_ATTRS: set[str] = {"__init__", "__class__"}


# ===================================================================
# Helpers
# ===================================================================


def _resolve_flet_class(name: str) -> type | None:
    """Return the Flet class/function for a top-level ``ft.<name>``."""
    obj = getattr(ft, name, None)
    if obj is not None and (inspect.isclass(obj) or callable(obj)):
        return obj
    return None


def _resolve_submodule_class(mod_name: str, cls_name: str):
    """Return the class for ``ft.<mod_name>.<cls_name>``."""
    mod_path = KNOWN_SUBMODULES.get(mod_name)
    if mod_path:
        try:
            mod = importlib.import_module(mod_path)
            return getattr(mod, cls_name, None)
        except ImportError:
            pass
    # Fallback: try via the ft namespace
    ns = getattr(ft, mod_name, None)
    if ns is not None:
        return getattr(ns, cls_name, None)
    return None


def _get_valid_params(cls) -> set[str] | None:
    """Return the set of keyword parameter names for *cls.__init__*."""
    try:
        sig = inspect.signature(cls.__init__)
    except (ValueError, TypeError):
        return None
    params = set(sig.parameters.keys()) - {"self"}
    # If **kwargs is present, anything is valid — skip check
    for p in sig.parameters.values():
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            return None
    return params


# ===================================================================
# AST Visitor
# ===================================================================


class FletAPIChecker(ast.NodeVisitor):
    """Walk an AST and collect Flet API issues."""

    def __init__(self, filepath: str, source: str):
        self.filepath = filepath
        self.source = source
        self.issues: list[str] = []

    # ---- ft.Class(...) constructor calls ----------------------------------

    def visit_Call(self, node: ast.Call):
        func = node.func

        # Pattern 1: ft.ClassName(kw=...)
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "ft"
        ):
            cls_name = func.attr
            cls = _resolve_flet_class(cls_name)
            if cls is not None:
                self._check_kwargs(node, f"ft.{cls_name}", cls)

        # Pattern 2: ft.sub.ClassName(kw=...)  e.g. ft.dropdown.Option(...)
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "ft"
        ):
            sub_name = func.value.attr
            cls_name = func.attr
            cls = _resolve_submodule_class(sub_name, cls_name)
            if cls is not None:
                self._check_kwargs(node, f"ft.{sub_name}.{cls_name}", cls)

        self.generic_visit(node)

    def _check_kwargs(self, node: ast.Call, display_name: str, cls):
        # First check if we have a manual override (for classes with **kwargs)
        cls_name = cls.__name__
        if cls_name in KWARGS_OVERRIDE:
            valid = KWARGS_OVERRIDE[cls_name]
        else:
            valid = _get_valid_params(cls)
            if valid is None:
                return  # accepts **kwargs and no override — nothing to validate
        for kw in node.keywords:
            if kw.arg is None:
                continue  # **spread — skip
            if kw.arg not in valid:
                # Build helpful suggestion
                close = _closest_match(kw.arg, valid)
                hint = f"  (did you mean '{close}'?)" if close else ""
                self.issues.append(
                    f"{self.filepath}:{node.lineno}: "
                    f"{display_name}() has no parameter '{kw.arg}'{hint}\n"
                    f"    Valid params: {sorted(valid)}"
                )

    # ---- ft.Namespace.ATTR access  (enums, constants) --------------------

    def visit_Attribute(self, node: ast.Attribute):
        val = node.value

        if not (
            isinstance(val, ast.Attribute)
            and isinstance(val.value, ast.Name)
            and val.value.id == "ft"
        ):
            self.generic_visit(node)
            return

        ns_name = val.attr  # e.g. 'Alignment', 'padding', 'dropdown'
        attr_name = node.attr  # e.g. 'CENTER', 'only', 'Option'

        # --- Case 1: Known valid sub-modules (e.g. ft.dropdown.Option) ---
        if ns_name in VALID_LOWERCASE_MODULES:
            self.generic_visit(node)
            return

        # --- Case 2: Known deprecated lowercase helpers ---
        # e.g. ft.padding.only -> should be ft.Padding.only
        if ns_name in DEPRECATED_LOWERCASE_HELPERS:
            replacement = DEPRECATED_LOWERCASE_HELPERS[ns_name]
            self.issues.append(
                f"{self.filepath}:{node.lineno}: DEPRECATED -- "
                f"ft.{ns_name}.{attr_name}() deprecated since 0.80.0, "
                f"use ft.{replacement}.{attr_name}() instead"
            )
            self.generic_visit(node)
            return

        # --- Case 3: Lowercase namespace that's NOT a known helper ---
        # e.g. ft.alignment.center (this is a real error, not just deprecated)
        if ns_name[0].islower():
            camel = ns_name[0].upper() + ns_name[1:]
            if hasattr(ft, camel) and inspect.isclass(getattr(ft, camel)):
                self.issues.append(
                    f"{self.filepath}:{node.lineno}: ERROR -- "
                    f"ft.{ns_name}.{attr_name} is invalid. "
                    f"Use ft.{camel}.{attr_name.upper()} instead"
                )
            self.generic_visit(node)
            return

        # --- Case 4: CamelCase namespace — validate attribute exists ---
        ns_obj = getattr(ft, ns_name, None)
        if ns_obj is None:
            self.issues.append(
                f"{self.filepath}:{node.lineno}: ERROR -- "
                f"ft.{ns_name} does not exist in flet {ft.__version__}"
            )
        elif not hasattr(ns_obj, attr_name):
            self.issues.append(
                f"{self.filepath}:{node.lineno}: ERROR -- "
                f"ft.{ns_name}.{attr_name} does not exist. "
                f"Check the Flet {ft.__version__} docs."
            )

        self.generic_visit(node)


# ===================================================================
# Regex-based deprecated pattern checks
# ===================================================================


def _check_deprecated(filepath: str, source: str) -> list[str]:
    issues = []
    for pattern, msg in DEPRECATED_PATTERNS:
        for m in re.finditer(pattern, source):
            lineno = source[: m.start()].count("\n") + 1
            issues.append(f"{filepath}:{lineno}: DEPRECATED — {msg}")
    return issues


# ===================================================================
# String similarity for suggestions
# ===================================================================


def _closest_match(name: str, candidates: set[str]) -> str | None:
    """Return the closest match from *candidates* using simple edit distance."""
    best, best_dist = None, 999
    name_lower = name.lower()
    for c in candidates:
        # Simple: check prefix / substring
        if c.lower().startswith(name_lower) or name_lower.startswith(c.lower()):
            d = abs(len(c) - len(name))
            if d < best_dist:
                best, best_dist = c, d
        # Also check Levenshtein-ish
        d = _edit_distance(name_lower, c.lower())
        if d < best_dist:
            best, best_dist = c, d
    return best if best_dist <= 3 else None


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (basic DP)."""
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j in range(1, len(b) + 1):
        curr = [j] + [0] * len(a)
        for i in range(1, len(a) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(curr[i - 1] + 1, prev[i] + 1, prev[i - 1] + cost)
        prev = curr
    return prev[-1]


# ===================================================================
# Main
# ===================================================================


def check_file(filepath: str) -> list[str]:
    """Check a single file and return a list of issue strings."""
    full_path = PROJECT_ROOT / filepath
    if not full_path.exists():
        return [f"{filepath}: FILE NOT FOUND"]

    source = full_path.read_text(encoding="utf-8")

    # AST-based checks
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        return [f"{filepath}: SYNTAX ERROR — {exc}"]

    checker = FletAPIChecker(filepath, source)
    checker.visit(tree)
    issues = checker.issues

    # Regex-based deprecation checks
    issues.extend(_check_deprecated(filepath, source))

    return issues


def main():
    # Force UTF-8 output on Windows
    import io

    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print(f"[CHECK] Flet API Compatibility Checker -- flet v{ft.__version__}")
    print(f"   Project root: {PROJECT_ROOT}")
    print(f"   Checking {len(UI_FILES)} files...\n")

    all_issues: list[str] = []
    files_with_issues = 0

    for fpath in UI_FILES:
        issues = check_file(fpath)
        if issues:
            files_with_issues += 1
            for issue in issues:
                print(f"  [ISSUE] {issue}")
                print()
        all_issues.extend(issues)

    print("-" * 60)
    if all_issues:
        print(f"  [WARN] {len(all_issues)} issue(s) found in {files_with_issues} file(s)")
        sys.exit(1)
    else:
        print("  [OK] No Flet API issues found!")
        sys.exit(0)


if __name__ == "__main__":
    main()

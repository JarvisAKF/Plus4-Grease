"""Checks that Python files will run on the Plus 4's Python 3.7.

Run on a computer: python3 tools/py37check.py grease/*.py tools/*.py

It parses each file with the 3.7 grammar and looks for library calls and annotations added after 3.7. It can't catch
everything, so the printer's own run is still the real test, but it catches the usual slips before they get there.
"""
import ast
import pathlib
import re
import sys

NEWER = [
    (r"\.removeprefix\(|\.removesuffix\(", "str.removeprefix/removesuffix (3.9)"),
    (r"functools\.cache\b|from functools import [^\n]*\bcache\b", "functools.cache (3.9)"),
    (r"\bmath\.(lcm|nextafter|ulp)\b", "math function from 3.9"),
    (r"\bzoneinfo\b|\bgraphlib\b", "module from 3.9"),
    (r"importlib\.metadata", "importlib.metadata (3.8)"),
    (r"\bshlex\.join\b", "shlex.join (3.8)"),
    (r"\bmath\.(prod|isqrt|dist|comb|perm)\b", "math function from 3.8"),
    (r"\bcached_property\b", "functools.cached_property (3.8)"),
    (r"from typing import [^\n]*\b(TypedDict|Literal|Protocol|Final)\b", "typing name from 3.8"),
    (r"\bdataclass\([^)]*slots=", "dataclass slots (3.10)"),
    (r"\bzip\([^)]*strict=", "zip strict (3.10)"),
    (r"\.bit_count\(\)", "int.bit_count (3.10)"),
    (r"\basyncio\.to_thread\b", "asyncio.to_thread (3.9)"),
    (r"f[\"'][^\"'\n]*\{[^}\n]*=\}", "f-string = specifier (3.8)"),
]

BUILTIN_GENERICS = ("list", "dict", "tuple", "set", "frozenset", "type")


def annotation_problems(tree):
    problems = set()
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args.args + node.args.kwonlyargs
            annotations = [a.annotation for a in args if a.annotation] + ([node.returns] if node.returns else [])
        elif isinstance(node, ast.AnnAssign):
            annotations = [node.annotation]
        for annotation in annotations:
            for sub in ast.walk(annotation):
                if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name) and sub.value.id in BUILTIN_GENERICS:
                    problems.add("list[...]-style annotation without from __future__ import annotations (3.9)")
                if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                    problems.add("X | Y annotation without from __future__ import annotations (3.10)")
    return problems


def check(path):
    source = pathlib.Path(path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=path, feature_version=(3, 7))
    except SyntaxError as error:
        return ["3.7 syntax error, line {}: {}".format(error.lineno, error.msg)]
    problems = {why for pattern, why in NEWER if re.search(pattern, source, re.M)}
    if "from __future__ import annotations" not in source:
        problems |= annotation_problems(tree)
    return sorted(problems)


def main(paths):
    me = pathlib.Path(__file__).resolve()
    paths = [path for path in paths if pathlib.Path(path).resolve() != me]  # its patterns would match themselves
    bad = {path: check(path) for path in paths}
    bad = {path: problems for path, problems in bad.items() if problems}
    print("{} OK, {} with 3.7 problems".format(len(paths) - len(bad), len(bad)))
    for path, problems in sorted(bad.items()):
        print("  {}: {}".format(path, "; ".join(problems)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

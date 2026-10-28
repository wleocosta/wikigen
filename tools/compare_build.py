#!/usr/bin/env python3
"""Compare every hand-written page with its generated twin in build/.

Compares the <head> and the <main> content; the header, footer and scripts are
expected to differ. Run after:  python tools/build.py
"""
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ["en", "pt"]


def section(html, tag):
    match = re.search(rf"<{tag}>(.*?)</{tag}>", html, re.S)
    return [line.rstrip() for line in match.group(1).strip().splitlines()] if match else None


def main():
    pages = differences = 0
    for lang in LANGS:
        for src in sorted((ROOT / lang).rglob("*.html")):
            rel = src.relative_to(ROOT)
            twin = ROOT / "build" / rel
            pages += 1
            if not twin.exists():
                print(f"{rel.as_posix()}: no generated page")
                differences += 1
                continue
            old = src.read_text(encoding="utf-8")
            new = twin.read_text(encoding="utf-8")
            for tag in ("head", "main"):
                a, b = section(old, tag), section(new, tag)
                if a != b:
                    differences += 1
                    print(f"{rel.as_posix()}: <{tag}> differs")
                    diff = difflib.unified_diff(a or [], b or [], "hand-written", "generated", lineterm="", n=0)
                    for line in list(diff)[:8]:
                        print("    " + line)
    if differences:
        print(f"\nCompared {pages} pages: {differences} difference(s)")
        sys.exit(1)
    print(f"Compared {pages} pages: all identical (head and main)")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""One-time migration: turn the hand-written pages in en/ and pt/ into content files.

Run from the repository root:  python tools/import_pages.py [--force]
Writes content/<lang>/<path>.html and keeps files that already exist.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ["en", "pt"]


def convert(src):
    html = src.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
    description = re.search(r'<meta name="description" content="(.*?)">', html, re.S).group(1)
    main = re.search(r"[ \t]*<main>\n(.*?)\n[ \t]*</main>", html, re.S).group(1)
    for name, value in (("title", title), ("description", description)):
        if "\n" in value:
            raise SystemExit(f"{src}: the {name} spans several lines; put it on one line first")
    sources = re.findall(r'<script src="([^"]+)"', html)
    scripts = [re.sub(r"^(\.\./)+", "", s) for s in sources if not s.endswith("layout.js")]
    head = f"title: {title}\ndescription: {description}\n"
    if scripts:
        head += "scripts: " + ", ".join(scripts) + "\n"
    return head + "---\n" + main + "\n"


def main():
    force = "--force" in sys.argv
    imported = kept = 0
    for lang in LANGS:
        for src in sorted((ROOT / lang).rglob("*.html")):
            dest = ROOT / "content" / lang / src.relative_to(ROOT / lang)
            if dest.exists() and not force:
                kept += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="\n") as f:
                f.write(convert(src))
            imported += 1
    print(f"Imported {imported} page(s), kept {kept} existing")


if __name__ == "__main__":
    main()
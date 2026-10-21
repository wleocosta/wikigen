#!/usr/bin/env python3
"""Site checker. Run from the repository root:  python tools/check_site.py

Checks every page under en/ for:
  - broken internal links and missing anchors
  - red links (class="new") that point to pages that now exist
  - missing or duplicated <title>, missing or long meta description
  - a <title> that differs from the <h1>
  - a wrong data-root attribute (used by js/layout.js)
  - missing CSS or JavaScript files
It also lists external links, which must be verified by hand.
"""
import pathlib
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

ROOT = pathlib.Path("en")
MAX_DESCRIPTION = 160


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []          # (href, is_red_link)
        self.ids = set()         # every id="..." on the page (anchor targets)
        self.title = ""
        self.h1 = ""
        self.description = ""
        self.lang = None
        self.data_root = None
        self.assets = []         # CSS and JS files
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "meta" and a.get("name") == "description":
            self.description = a.get("content", "")
        elif tag == "body":
            self.data_root = a.get("data-root")
        elif tag == "a" and "href" in a:
            self.links.append((a["href"], "new" in (a.get("class") or "").split()))
        elif tag == "script" and "src" in a:
            self.assets.append(a["src"])
        elif tag == "link" and a.get("rel") == "stylesheet" and "href" in a:
            self.assets.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_h1:
            self.h1 += data


def main():
    pages = sorted(ROOT.rglob("*.html"))
    parsed = {}
    for page in pages:
        parser = PageParser()
        parser.feed(page.read_text(encoding="utf-8"))
        parsed[page.resolve()] = parser

    problems = []
    externals = []
    titles = {}

    def flag(page, message):
        problems.append(f"{page.as_posix()}: {message}")

    for page in pages:
        p = parsed[page.resolve()]
        title = p.title.strip()

        # Metadata: information about the page, not part of its content
        if not title:
            flag(page, "missing <title>")
        else:
            titles.setdefault(title, []).append(page)
            if p.h1.strip() and p.h1.strip() != title:
                flag(page, f'<title> "{title}" differs from <h1> "{p.h1.strip()}"')
        if not p.description.strip():
            flag(page, "missing meta description")
        elif len(p.description) > MAX_DESCRIPTION:
            flag(page, f"description has {len(p.description)} characters (limit {MAX_DESCRIPTION})")
        if p.lang != "en":
            flag(page, f'<html lang> is "{p.lang}", expected "en"')

        # data-root must match the folder depth
        depth = len(page.relative_to(ROOT).parts) - 1
        expected = "../" * depth
        if (p.data_root or "") != expected:
            flag(page, f'data-root is "{p.data_root}", expected "{expected}"')

        # CSS and JavaScript files
        for ref in p.assets:
            if not urlparse(ref).scheme and not (page.parent / ref).resolve().exists():
                flag(page, f"missing file: {ref}")

        # Links
        for href, is_red in p.links:
            url = urlparse(href)
            if url.scheme in ("http", "https"):
                externals.append((page, href))
                continue
            if url.scheme:                       # mailto:, tel:, etc.
                continue
            path = unquote(url.path)
            target = page.resolve() if path == "" else (page.parent / path).resolve()
            exists = target.exists()
            if is_red and exists:
                flag(page, f"red link to a page that exists: {href}")
            if not is_red and not exists:
                flag(page, f"broken link: {href}")
            if exists and url.fragment and target in parsed:
                if url.fragment not in parsed[target].ids:
                    flag(page, f"missing anchor: {href}")

    for title, same in titles.items():
        if len(same) > 1:
            names = ", ".join(x.as_posix() for x in same)
            problems.append(f'duplicate title "{title}": {names}')

    print(f"Checked {len(pages)} pages.")
    if problems:
        print(f"\n{len(problems)} problem(s) found:")
        for line in problems:
            print("  -", line)
    else:
        print("No problems found.")

    print(f"\nExternal links to verify by hand ({len(externals)}):")
    for page, href in externals:
        print(f"  {page.as_posix()}  ->  {href}")

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
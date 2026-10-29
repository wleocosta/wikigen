#!/usr/bin/env python3
"""Minimal site generator. Run from the repository root:

    python tools/build.py                       write the pages into build/ (ignored by Git)
    python tools/build.py --publish             write the pages into en/, pt/, ... in the root
    python tools/build.py add-lang es Español   register a new language
    python tools/build.py status                show how many pages exist in each language

Reads site.json, i18n/<code>.json, templates/page.html and content/<code>/**/*.html.

A content file has a small header (front matter), a line with three dashes, and
the HTML that goes inside <main>:

    title: Main Page
    description: One sentence for search engines.
    scripts: js/board.js, js/other.js      (optional)
    ---
    <h1>Main Page</h1>
    ...
"""
import argparse
import json
import re
import shutil
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
OUT = ROOT / "build"
RTL_LANGS = {"he", "ar", "fa", "ur"}   # right-to-left languages


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, text):
    """Write a file with LF line endings, whatever the operating system."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def parse_page(path):
    """Split a content file into its front matter (a dict) and its HTML body."""
    head, sep, body = path.read_text(encoding="utf-8").partition("\n---\n")
    if not sep:
        raise SystemExit(f"{path}: missing the --- line after the front matter")
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    for key in ("title", "description"):
        if key not in meta:
            raise SystemExit(f"{path}: missing '{key}' in the front matter")
    return meta, body.strip("\n")


def page_url(depth, code, rel):
    """Address of content/<code>/<rel>, written from a page at this depth."""
    return "../" * (depth + 1) + f"{code}/{rel.as_posix()}"


def render_alternates(site, uis, lang, rel, existing):
    """<link rel="alternate" hreflang=...> lines; empty when the page has no translation."""
    if len(existing) < 2:
        return ""
    depth = len(rel.parts) - 1
    default = site["languages"][0]
    lines = []
    for code in existing:
        href = rel.name if code == lang else page_url(depth, code, rel)
        lines.append(f'  <link rel="alternate" hreflang="{uis[code]["html_lang"]}" href="{href}">')
    fallback = default if default in existing else existing[0]
    default_href = rel.name if fallback == lang else page_url(depth, fallback, rel)
    lines.append(f'  <link rel="alternate" hreflang="x-default" href="{default_href}">')
    return "\n".join(lines) + "\n"


def render_menu(site, uis, lang, rel, pages):
    """Menu links; a page missing in this language links to the default language's page."""
    ui = uis[lang]
    default = site["languages"][0]
    depth = len(rel.parts) - 1
    items = []
    for key, href in site["menu"]:
        target = Path(href)
        if target in pages[lang]:
            link, extra = "../" * depth + href, ""
        else:
            link = page_url(depth, default, target)
            extra = f' hreflang="{uis[default]["html_lang"]}"'
        current = ' aria-current="page"' if rel.as_posix() == href else ""
        items.append(f'<li><a href="{link}"{extra}{current}>{ui["menu"][key]}</a></li>')
    return "".join(items)


def render_switcher(uis, lang, rel, existing):
    """Language switcher; empty when the page exists in only one language."""
    if len(existing) < 2:
        return ""
    depth = len(rel.parts) - 1
    items = []
    for code in existing:
        ui = uis[code]
        if code == lang:
            items.append(f'<li><span aria-current="true" lang="{ui["html_lang"]}">{ui["lang_name"]}</span></li>')
        else:
            href = page_url(depth, code, rel)
            items.append(f'<li><a href="{href}" hreflang="{ui["html_lang"]}" lang="{ui["html_lang"]}">{ui["lang_name"]}</a></li>')
    return (f'<nav aria-label="{uis[lang]["lang_label"]}"><ul class="lang-switcher">'
            + "".join(items) + "</ul></nav>")


def render_scripts(meta, depth):
    sources = [s.strip() for s in meta.get("scripts", "").split(",") if s.strip()]
    prefix = "../" * (depth + 1)
    return "".join(f'  <script src="{prefix}{s}" defer></script>\n' for s in sources)


def prepare_output(publish, languages, pages):
    """Return the output folder, cleaned and ready for the generated pages."""
    if not publish:
        if OUT.exists():
            shutil.rmtree(OUT)
        for asset in ("css", "js"):
            if (ROOT / asset).is_dir():
                shutil.copytree(ROOT / asset, OUT / asset)
        return OUT

    # Publish mode: refuse to delete anything the generator does not create
    unknown = []
    for code in languages:
        folder = ROOT / code
        if folder.is_dir():
            unknown += [p for p in folder.rglob("*")
                        if p.is_file() and (p.suffix != ".html" or p.relative_to(folder) not in pages[code])]
    if unknown:
        names = "\n  ".join(p.relative_to(ROOT).as_posix() for p in unknown)
        raise SystemExit("Refusing to publish: these files have no content file:\n  " + names)
    for code in languages:
        if (ROOT / code).is_dir():
            shutil.rmtree(ROOT / code)
    return ROOT


def build(publish=False):
    site = load_json(ROOT / "site.json")
    languages = site["languages"]
    uis = {code: load_json(ROOT / "i18n" / f"{code}.json") for code in languages}
    template = Template((ROOT / "templates" / "page.html").read_text(encoding="utf-8"))

    pages = {}  # language code -> list of page paths inside content/<code>/
    for code in languages:
        folder = CONTENT / code
        pages[code] = sorted(p.relative_to(folder) for p in folder.rglob("*.html")) if folder.is_dir() else []

    out = prepare_output(publish, languages, pages)

    count = 0
    for lang in languages:
        ui = uis[lang]
        for rel in pages[lang]:
            existing = [code for code in languages if rel in pages[code]]
            meta, body = parse_page(CONTENT / lang / rel)
            depth = len(rel.parts) - 1
            html = template.substitute(
                html_lang=ui["html_lang"],
                dir=ui["dir"],
                title=meta["title"],
                description=meta["description"].replace('"', "&quot;"),
                alternates=render_alternates(site, uis, lang, rel, existing),
                css_path="../" * (depth + 1) + "css/style.css",
                home="../" * depth + "index.html",
                site_title=ui["site_title"],
                nav_label=ui["nav_label"],
                nav=render_menu(site, uis, lang, rel, pages),
                switcher=render_switcher(uis, lang, rel, existing),
                content=body,
                footer=ui["footer"],
                scripts=render_scripts(meta, depth),
            )
            write(out / lang / rel, html)
            count += 1
    print(f"Built {count} page(s) into {out.relative_to(ROOT).as_posix()}/")


def add_lang(code, name):
    """Register a new language: interface file, content folder and site.json entry."""
    site_path = ROOT / "site.json"
    site = load_json(site_path)
    if code in site["languages"]:
        raise SystemExit(f"Language already registered: {code}")

    # Start from the default language's interface file; its values are translated afterwards
    default = site["languages"][0]
    ui = load_json(ROOT / "i18n" / f"{default}.json")
    ui["lang_name"] = name
    ui["html_lang"] = code
    ui["dir"] = "rtl" if code.split("-")[0] in RTL_LANGS else "ltr"
    write(ROOT / "i18n" / f"{code}.json", json.dumps(ui, indent=2, ensure_ascii=False) + "\n")
    (CONTENT / code).mkdir(parents=True, exist_ok=True)

    # Change only the "languages" line, so the rest of site.json keeps its formatting
    text = site_path.read_text(encoding="utf-8")
    new_list = '"languages": ' + json.dumps(site["languages"] + [code])
    text = re.sub(r'"languages":\s*\[[^\]]*\]', lambda m: new_list, text, count=1)
    write(site_path, text)

    print(f"Added '{code}' ({name}, {ui['dir']}).")
    print(f"Next: translate the values in i18n/{code}.json, then add content/{code}/index.html")


def status():
    """Show how many pages exist in each language."""
    site = load_json(ROOT / "site.json")
    default_dir = CONTENT / site["languages"][0]
    pages = sorted(p.relative_to(default_dir) for p in default_dir.rglob("*.html"))
    for code in site["languages"]:
        done = sum((CONTENT / code / p).exists() for p in pages)
        print(f"{code:8} {done}/{len(pages)} pages")


def main():
    parser = argparse.ArgumentParser(description="Minimal static-site generator")
    parser.add_argument("--publish", action="store_true",
                        help="write the pages into en/, pt/, ... instead of build/")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("add-lang", help="register a new language")
    p.add_argument("code", help="language code, also the folder name, e.g. es or zh-Hans")
    p.add_argument("name", help="language name in its own language, e.g. Español")
    sub.add_parser("status", help="show how many pages exist in each language")
    args = parser.parse_args()
    if args.command == "add-lang":
        add_lang(args.code, args.name)
    elif args.command == "status":
        status()
    else:
        build(publish=args.publish)


if __name__ == "__main__":
    main()
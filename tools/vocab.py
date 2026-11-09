#!/usr/bin/env python3
"""Vocabulary and sentence-pattern database for the wiki project.

Run it from the project root:

    python tools/vocab.py init
    python tools/vocab.py import FILE.tsv [--dry-run] [--lang en]
    python tools/vocab.py add [--lang en]
    python tools/vocab.py search TEXT [--limit 20]
    python tools/vocab.py list [--topic TOPIC] [--limit 30]
    python tools/vocab.py stats
    python tools/vocab.py topics [--limit 500]
    python tools/vocab.py clean [--apply] [--samples 3]
    python tools/vocab.py retopic MAP.tsv [--apply]
    python tools/vocab.py pages [--out FILE] [--examples 2]
    python tools/vocab.py export FILE.tsv [--table vocabulary|pattern] [--header]
    python tools/vocab.py pattern-add [--lang en]
    python tools/vocab.py pattern-list [--priority 1|2|3] [--limit 30]

The database is one SQLite file, data/wiki.db, created automatically.
Only the Python standard library is used.

TSV columns (vocabulary, the same order as your lesson files):
    step, topic, term, definition_en, translation_pt, sentence_used, match, note
"""
import argparse
import csv
import html
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "wiki.db"

# Column order of the TSV files. "match" is stored as "matched" in the database.
VOCAB_FIELDS = ["step", "topic", "term", "definition_en", "translation_pt",
                "sentence_used", "matched", "note"]
PATTERN_FIELDS = ["pattern", "function", "example", "translation_pt",
                  "priority", "topic", "note"]

# Fragments of table markup (<tr>...</tr>) that were copied into the text columns.
TABLE_ROW = re.compile(r"\s*<tr\b[^>]*>.*?</tr\s*>\s*", re.IGNORECASE | re.DOTALL)
TABLE_LEFTOVER = re.compile(r"</?t[rdh]\b", re.IGNORECASE)
ANY_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>")
CLEAN_COLUMNS = ["topic", "definition_en", "translation_pt", "sentence_used", "note"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL DEFAULT 'en',
    step TEXT,
    topic TEXT,
    term TEXT NOT NULL COLLATE NOCASE,
    definition_en TEXT,
    translation_pt TEXT,
    sentence_used TEXT,
    matched TEXT,
    note TEXT,
    UNIQUE (lang, term)
);

CREATE TABLE IF NOT EXISTS pattern (
    id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL DEFAULT 'en',
    pattern TEXT NOT NULL,
    function TEXT,
    example TEXT,
    translation_pt TEXT,
    priority INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
    topic TEXT,
    note TEXT,
    UNIQUE (lang, pattern)
);
"""


# ---------------------------------------------------------------- helpers

def clean(value):
    """Collapse whitespace (tabs and newlines included) into single spaces."""
    return " ".join(str(value or "").split())


def connect(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def read_rows(path):
    """Yield (line number, list of cells) from a tab-separated file.

    The file is read as UTF-8 (a leading byte order mark is accepted).
    Cells quoted the way Google Sheets and Excel export them are understood:
    a cell wrapped in double quotes, with inner quotes doubled, is unwrapped.
    A double quote in the middle of a cell is an ordinary character.
    """
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if any(cell.strip() for cell in row):
                yield reader.line_num, row


def ask(prompt, default=""):
    suffix = " [%s]" % default if default else ""
    value = input("%s%s: " % (prompt, suffix)).strip()
    return value or default


def show_vocab(row):
    print("%s  ->  %s" % (row["term"], row["translation_pt"] or "-"))
    if row["definition_en"]:
        print("    %s" % row["definition_en"])
    if row["sentence_used"]:
        print("    e.g. %s" % row["sentence_used"])
    meta = " | ".join(x for x in (row["topic"], row["note"]) if x)
    if meta:
        print("    [%s]" % meta)


def show_pattern(row):
    label = " (%s)" % row["function"] if row["function"] else ""
    print("[P%d] %s%s" % (row["priority"], row["pattern"], label))
    if row["example"]:
        print("    e.g. %s" % row["example"])
    if row["translation_pt"]:
        print("    pt: %s" % row["translation_pt"])
    meta = " | ".join(x for x in (row["topic"], row["note"]) if x)
    if meta:
        print("    [%s]" % meta)


# --------------------------------------------------------------- commands

def cmd_init(args):
    conn = connect(args.db)
    words = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
    patterns = conn.execute("SELECT COUNT(*) FROM pattern").fetchone()[0]
    conn.close()
    print("Database ready: %s" % args.db)
    print("Vocabulary entries: %d | Sentence patterns: %d" % (words, patterns))


def cmd_import(args):
    conn = connect(args.db)
    read = inserted = merged = unchanged = 0
    problems = []

    for number, row in read_rows(args.file):
        row = [clean(cell) for cell in row]
        # A header row is accepted and ignored.
        if len(row) > 2 and row[0].lower() == "step" and row[2].lower() == "term":
            continue
        read += 1
        if len(row) > 8:  # stray tabs inside the note: keep them in the note
            row = row[:7] + [" ".join(row[7:])]
        row += [""] * (8 - len(row))
        step, topic, term, definition_en, translation_pt, sentence, matched, note = row

        if not term:
            problems.append("line %d: no term, skipped" % number)
            continue

        existing = conn.execute(
            "SELECT * FROM vocabulary WHERE lang = ? AND term = ?",
            (args.lang, term)).fetchone()

        if existing is None:
            conn.execute(
                "INSERT INTO vocabulary (lang, step, topic, term, definition_en,"
                " translation_pt, sentence_used, matched, note)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (args.lang, step, topic, term, definition_en, translation_pt,
                 sentence, matched, note))
            inserted += 1
            continue

        # The term already exists: fill empty fields, and keep every example sentence.
        changes = {}
        for name, value in (("step", step), ("topic", topic),
                            ("definition_en", definition_en),
                            ("translation_pt", translation_pt), ("note", note)):
            if value and not existing[name]:
                changes[name] = value
        if sentence:
            old = existing["sentence_used"] or ""
            if sentence.lower() not in old.lower():
                changes["sentence_used"] = (old + " | " + sentence) if old else sentence
        if changes:
            assignments = ", ".join("%s = ?" % name for name in changes)
            conn.execute("UPDATE vocabulary SET %s WHERE id = ?" % assignments,
                         list(changes.values()) + [existing["id"]])
            merged += 1
        else:
            unchanged += 1

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
    conn.close()

    print("%sRows read: %d" % ("DRY RUN (nothing saved). " if args.dry_run else "", read))
    print("  new entries:                    %d" % inserted)
    print("  existing entries updated:       %d" % merged)
    print("  repeated rows, nothing to add:  %d" % unchanged)
    print("  problems:                       %d" % len(problems))
    for message in problems[:10]:
        print("    " + message)
    print("Entries in the database%s: %d" % (" after the import" if not args.dry_run else "", total))


def cmd_add(args):
    conn = connect(args.db)
    term = clean(ask("Term"))
    if not term:
        print("Cancelled: no term.")
        return 1
    existing = conn.execute(
        "SELECT * FROM vocabulary WHERE lang = ? AND term = ?", (args.lang, term)).fetchone()
    if existing is not None:
        print("This term already exists:")
        show_vocab(existing)
        return 1
    topic = clean(ask("Topic"))
    definition = clean(ask("Definition in English"))
    translation = clean(ask("Translation in Portuguese"))
    sentence = clean(ask("Sentence in which it was used"))
    note = clean(ask("Note"))
    matched = ""
    if sentence:
        matched = "yes" if term.lower() in sentence.lower() else "no"
    conn.execute(
        "INSERT INTO vocabulary (lang, topic, term, definition_en, translation_pt,"
        " sentence_used, matched, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (args.lang, topic, term, definition, translation, sentence, matched, note))
    conn.commit()
    conn.close()
    print("Added: %s" % term)
    return 0


def cmd_search(args):
    conn = connect(args.db)
    like = "%" + args.text + "%"
    rows = conn.execute(
        "SELECT * FROM vocabulary WHERE term LIKE ? OR definition_en LIKE ?"
        " OR translation_pt LIKE ? OR sentence_used LIKE ? OR note LIKE ?"
        " ORDER BY term LIMIT ?", (like, like, like, like, like, args.limit)).fetchall()
    patterns = conn.execute(
        "SELECT * FROM pattern WHERE pattern LIKE ? OR example LIKE ?"
        " OR translation_pt LIKE ? OR function LIKE ? ORDER BY priority, pattern LIMIT ?",
        (like, like, like, like, args.limit)).fetchall()
    conn.close()
    if not rows and not patterns:
        print("Nothing found for: %s" % args.text)
        return 0
    for row in rows:
        show_vocab(row)
    if patterns:
        print("--- sentence patterns ---")
        for row in patterns:
            show_pattern(row)
    print("(%d entries, %d patterns)" % (len(rows), len(patterns)))
    return 0


def cmd_list(args):
    conn = connect(args.db)
    if args.topic:
        rows = conn.execute(
            "SELECT * FROM vocabulary WHERE topic LIKE ? ORDER BY id LIMIT ?",
            ("%" + args.topic + "%", args.limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM vocabulary ORDER BY id LIMIT ?",
                            (args.limit,)).fetchall()
    conn.close()
    for row in rows:
        show_vocab(row)
    print("(%d entries shown)" % len(rows))
    return 0


def cmd_stats(args):
    conn = connect(args.db)
    words = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
    print("Vocabulary entries: %d" % words)
    print("By topic:")
    for row in conn.execute(
            "SELECT COALESCE(NULLIF(topic, ''), '(no topic)') AS t, COUNT(*) AS n"
            " FROM vocabulary GROUP BY t ORDER BY n DESC, t LIMIT 20"):
        print("  %-22s %d" % (row["t"], row["n"]))
    patterns = conn.execute("SELECT COUNT(*) FROM pattern").fetchone()[0]
    print("Sentence patterns: %d" % patterns)
    for row in conn.execute(
            "SELECT priority, COUNT(*) AS n FROM pattern GROUP BY priority ORDER BY priority"):
        print("  priority %d: %d" % (row["priority"], row["n"]))
    conn.close()
    return 0


def cmd_topics(args):
    conn = connect(args.db)
    rows = conn.execute(
        "SELECT COALESCE(NULLIF(topic, ''), '(no topic)') AS t, COUNT(*) AS n"
        " FROM vocabulary GROUP BY t ORDER BY n DESC, t").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
    conn.close()
    print("%d distinct topics, %d entries" % (len(rows), total))
    for row in rows[:args.limit]:
        print("%4d  %s" % (row["n"], row["t"]))
    return 0


def snippet(text, width=110):
    text = clean(text)
    return text if len(text) <= width else text[:width - 3] + "..."


def cmd_clean(args):
    """Remove pasted table-row markup from the text columns (preview unless --apply)."""
    conn = connect(args.db)
    rows = conn.execute("SELECT * FROM vocabulary ORDER BY id").fetchall()
    per_column = {name: 0 for name in CLEAN_COLUMNS}
    updates, samples, leftovers, other = [], [], [], []

    for row in rows:
        new = {}
        for name in CLEAN_COLUMNS:
            old = row[name] or ""
            if "<" not in old:
                continue
            fixed = clean(TABLE_ROW.sub(" ", old))
            if fixed != clean(old):
                new[name] = fixed
                per_column[name] += 1
                if len(samples) < args.samples:
                    samples.append((row["term"], name, old, fixed))
            if TABLE_LEFTOVER.search(fixed):
                leftovers.append((row["term"], name, fixed))
            elif ANY_TAG.search(fixed):
                other.append((row["term"], name, fixed))
        if new:
            updates.append((row["id"], new))

    print("Entries with table-row markup in the text columns: %d" % len(updates))
    for name in CLEAN_COLUMNS:
        print("  %-15s %d" % (name, per_column[name]))
    for term, name, old, fixed in samples:
        print("--- %s (%s)" % (term, name))
        print("  before: %s" % snippet(old))
        print("  after:  %s" % (snippet(fixed) if fixed else "(empty)"))
    print("Unbalanced table markup left after cleaning: %d" % len(leftovers))
    for term, name, text in leftovers[:5]:
        print("    %s (%s): %s" % (term, name, snippet(text, 90)))
    print("Other HTML tags found (left untouched): %d" % len(other))
    for term, name, text in other[:5]:
        print("    %s (%s): %s" % (term, name, snippet(text, 90)))

    if not args.apply:
        print("Preview only, nothing changed. Run again with --apply to save the cleanup.")
        conn.close()
        return 0
    for row_id, new in updates:
        assignments = ", ".join("%s = ?" % name for name in new)
        conn.execute("UPDATE vocabulary SET %s WHERE id = ?" % assignments,
                     list(new.values()) + [row_id])
    conn.commit()
    conn.close()
    print("Cleanup saved: %d entries updated." % len(updates))
    return 0


def read_topic_map(path):
    """Read a map file: one 'old topic <TAB> new topic' pair per line.

    Lines that start with # and a header line (old, new) are ignored.
    """
    mapping, problems = {}, []
    for number, row in read_rows(path):
        row = [clean(cell) for cell in row]
        if row[0].startswith("#"):
            continue
        if len(row) < 2 or not row[0] or not row[1]:
            problems.append("line %d: needs two columns (old topic, new topic)" % number)
            continue
        if row[0].lower() == "old" and row[1].lower() == "new":
            continue
        key = row[0].lower()
        if key in mapping and mapping[key][1] != row[1]:
            problems.append("line %d: '%s' is mapped twice with different results" % (number, row[0]))
            continue
        mapping[key] = (row[0], row[1])
    return mapping, problems


def cmd_retopic(args):
    """Rename topics with a map file (preview unless --apply)."""
    mapping, problems = read_topic_map(args.file)
    if problems:
        for message in problems:
            print("Problem in the map file: " + message)
        return 1
    conn = connect(args.db)
    current = {row["topic"]: row["n"] for row in conn.execute(
        "SELECT topic, COUNT(*) AS n FROM vocabulary WHERE topic IS NOT NULL AND topic != ''"
        " GROUP BY topic")}
    renames, result, untouched = [], {}, []
    for topic, count in current.items():
        target = mapping.get(topic.lower(), (None, None))[1]
        if target and target != topic:
            renames.append((topic, target, count))
            result[target] = result.get(target, 0) + count
        else:
            if not target:
                untouched.append(topic)
            result[topic] = result.get(topic, 0) + count
    unused = [old for key, (old, new) in mapping.items()
              if key not in {t.lower() for t in current}]

    moved = sum(count for _, _, count in renames)
    print("Topics in the database: %d | map entries: %d" % (len(current), len(mapping)))
    print("Entries that would change topic: %d (from %d old topics)" % (moved, len(renames)))
    print("Topics after the change: %d" % len(result))
    for topic, count in sorted(result.items(), key=lambda item: (-item[1], item[0])):
        print("  %4d  %s" % (count, topic))
    print("Topics not in the map, left as they are (%d): %s" % (len(untouched), ", ".join(sorted(untouched)) or "-"))
    print("Map entries that match no topic in the database (%d): %s" % (len(unused), ", ".join(unused) or "-"))

    if not args.apply:
        print("Preview only, nothing changed. Run again with --apply to save the new topics.")
        conn.close()
        return 0
    for old, new, _ in renames:
        conn.execute("UPDATE vocabulary SET topic = ? WHERE topic = ?", (new, old))
    conn.commit()
    conn.close()
    print("Topics saved: %d entries updated." % moved)
    return 0


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "topic"


def cmd_pages(args):
    """Generate the Vocabulary article (an ordinary content file) from the database."""
    conn = connect(args.db)
    rows = conn.execute(
        "SELECT * FROM vocabulary WHERE lang = ?"
        " ORDER BY topic COLLATE NOCASE, term COLLATE NOCASE", (args.lang,)).fetchall()
    conn.close()
    if not rows:
        print("The database has no vocabulary entries for language '%s'." % args.lang)
        return 1

    esc = html.escape
    groups = {}
    for row in rows:
        groups.setdefault(row["topic"] or "Other", []).append(row)
    names = sorted(groups, key=str.lower)

    title = "Vocabulary"
    description = ("Personal English vocabulary: terms with definitions, Portuguese "
                   "translations and example sentences, grouped by topic.")
    if len(description) > 160:
        print("Warning: the description has %d characters (limit 160)." % len(description))

    out = []
    out.append("title: %s" % title)
    out.append("description: %s" % description)
    out.append("---")
    out.append("    <h1>%s</h1>" % title)
    out.append('    <p class="hatnote">This article is part of the <a href="index.html">Languages</a> category.</p>')
    out.append("")
    out.append('    <table class="infobox">')
    out.append("      <caption>Vocabulary</caption>")
    out.append('      <tr><th scope="row">Category</th><td>Language learning</td></tr>')
    out.append('      <tr><th scope="row">Entries</th><td>%d</td></tr>' % len(rows))
    out.append('      <tr><th scope="row">Topics</th><td>%d</td></tr>' % len(names))
    out.append('      <tr><th scope="row">Languages</th><td>English, with Portuguese translations</td></tr>')
    out.append('      <tr><th scope="row">Related</th><td><a href="index.html">Languages</a></td></tr>')
    out.append("    </table>")
    out.append("")
    out.append("    <p>")
    out.append("      <strong>Vocabulary</strong> is the set of words and expressions that a")
    out.append("      person knows and can use. This page lists the English terms studied while")
    out.append("      building this encyclopedia. Each entry gives a definition, a Portuguese")
    out.append("      translation and an example sentence, and the terms are grouped by topic.")
    out.append("      Learning first the terms that appear most often gives the greatest return")
    out.append("      for the time spent.")
    out.append("    </p>")
    out.append("")
    out.append('    <nav class="toc" aria-labelledby="toc-title">')
    out.append('      <h2 id="toc-title">Contents</h2>')
    out.append("      <ol>")
    for name in names:
        out.append('        <li><a href="#%s">%s</a> (%d)</li>' % (slugify(name), esc(name), len(groups[name])))
    out.append('        <li><a href="#see-also">See also</a></li>')
    out.append("      </ol>")
    out.append("    </nav>")

    for name in names:
        out.append("")
        out.append('    <h2 id="%s">%s</h2>' % (slugify(name), esc(name)))
        out.append('    <div class="table-wrap">')
        out.append('      <table class="wikitable">')
        out.append("        <caption>%s: %d entries</caption>" % (esc(name), len(groups[name])))
        out.append("        <thead>")
        out.append('          <tr><th scope="col">Term</th><th scope="col">Portuguese</th>'
                   '<th scope="col">Definition</th><th scope="col">Example</th></tr>')
        out.append("        </thead>")
        out.append("        <tbody>")
        for row in groups[name]:
            examples = [e.strip() for e in (row["sentence_used"] or "").split(" | ") if e.strip()]
            example_html = "<br>".join(esc(e) for e in examples[:args.examples]) or "\u2014"
            out.append(
                '          <tr><td><strong>%s</strong></td><td lang="pt">%s</td><td>%s</td><td>%s</td></tr>'
                % (esc(row["term"]), esc(row["translation_pt"] or "\u2014"),
                   esc(row["definition_en"] or "\u2014"), example_html))
        out.append("        </tbody>")
        out.append("      </table>")
        out.append("    </div>")

    out.append("")
    out.append('    <h2 id="see-also">See also</h2>')
    out.append("    <ul>")
    out.append('      <li><a href="index.html">Languages</a>: category overview.</li>')
    out.append("    </ul>")

    target = Path(args.out) if args.out else ROOT / "content" / args.lang / "languages" / "vocabulary.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(out) + "\n")
    size = target.stat().st_size
    print("Wrote %d entries in %d topics to %s (%d KB)" % (len(rows), len(names), target, (size + 1023) // 1024))
    return 0


def cmd_export(args):
    conn = connect(args.db)
    if args.table == "pattern":
        fields, query = PATTERN_FIELDS, "SELECT * FROM pattern ORDER BY priority, id"
        header = PATTERN_FIELDS
    else:
        fields, query = VOCAB_FIELDS, "SELECT * FROM vocabulary ORDER BY id"
        header = [name if name != "matched" else "match" for name in VOCAB_FIELDS]
    rows = conn.execute(query).fetchall()
    conn.close()
    with open(args.file, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        if args.header:
            writer.writerow(header)
        for row in rows:
            writer.writerow([clean(row[name]) for name in fields])
    print("Exported %d rows (%s) to %s" % (len(rows), args.table, args.file))
    return 0


def cmd_pattern_add(args):
    conn = connect(args.db)
    pattern = clean(ask("Pattern (the reusable frame, e.g. X is the use of Y to do Z)"))
    if not pattern:
        print("Cancelled: no pattern.")
        return 1
    function = clean(ask("Function (definition, scope, comparison, cause and effect, sequence...)"))
    example = clean(ask("Example sentence"))
    translation = clean(ask("Translation in Portuguese"))
    priority_text = ask("Priority (1 = essential, 2 = useful, 3 = optional)", "2")
    topic = clean(ask("Topic"))
    note = clean(ask("Note"))
    if priority_text not in ("1", "2", "3"):
        print("Priority must be 1, 2 or 3. Nothing was saved.")
        return 1
    try:
        conn.execute(
            "INSERT INTO pattern (lang, pattern, function, example, translation_pt,"
            " priority, topic, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (args.lang, pattern, function, example, translation,
             int(priority_text), topic, note))
    except sqlite3.IntegrityError:
        print("This pattern already exists.")
        return 1
    conn.commit()
    conn.close()
    print("Added pattern: %s" % pattern)
    return 0


def cmd_pattern_list(args):
    conn = connect(args.db)
    if args.priority:
        rows = conn.execute(
            "SELECT * FROM pattern WHERE priority = ? ORDER BY id LIMIT ?",
            (args.priority, args.limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM pattern ORDER BY priority, id LIMIT ?",
                            (args.limit,)).fetchall()
    conn.close()
    for row in rows:
        show_pattern(row)
    print("(%d patterns shown)" % len(rows))
    return 0


# ------------------------------------------------------------------- main

def build_parser():
    parser = argparse.ArgumentParser(
        description="Vocabulary and sentence-pattern database for the wiki project.")
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help="database file (default: data/wiki.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the database and show its size")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("import", help="import vocabulary rows from a TSV file")
    p.add_argument("file")
    p.add_argument("--lang", default="en")
    p.add_argument("--dry-run", action="store_true", help="show the result without saving")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("add", help="add one vocabulary entry (interactive)")
    p.add_argument("--lang", default="en")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("search", help="search vocabulary and patterns")
    p.add_argument("text")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("list", help="list vocabulary entries")
    p.add_argument("--topic")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("stats", help="show counts")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("topics", help="list every topic with its number of entries")
    p.add_argument("--limit", type=int, default=500)
    p.set_defaults(func=cmd_topics)

    p = sub.add_parser("clean", help="remove pasted table-row markup (preview unless --apply)")
    p.add_argument("--apply", action="store_true", help="save the cleanup")
    p.add_argument("--samples", type=int, default=3, help="before/after examples to show")
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser("retopic", help="rename topics with a map file (preview unless --apply)")
    p.add_argument("file", help="TSV file: old topic, new topic")
    p.add_argument("--apply", action="store_true", help="save the new topics")
    p.set_defaults(func=cmd_retopic)

    p = sub.add_parser("pages", help="generate the Vocabulary article from the database")
    p.add_argument("--lang", default="en")
    p.add_argument("--out", help="output file (default: content/en/languages/vocabulary.html)")
    p.add_argument("--examples", type=int, default=2, help="example sentences per entry")
    p.set_defaults(func=cmd_pages)

    p = sub.add_parser("export", help="write a TSV file")
    p.add_argument("file")
    p.add_argument("--table", choices=["vocabulary", "pattern"], default="vocabulary")
    p.add_argument("--header", action="store_true", help="write a header row")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("pattern-add", help="add one sentence pattern (interactive)")
    p.add_argument("--lang", default="en")
    p.set_defaults(func=cmd_pattern_add)

    p = sub.add_parser("pattern-list", help="list sentence patterns")
    p.add_argument("--priority", type=int, choices=[1, 2, 3])
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_pattern_list)
    return parser


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1
    except FileNotFoundError as error:
        print("File not found: %s" % error.filename)
        return 1
    except BrokenPipeError:
        # The reader (for example "| head -n 3") closed the pipe early: normal.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Vocabulary and sentence-pattern database for the wiki project.

Run it from the project root:

    python tools/vocab.py init
    python tools/vocab.py import FILE.tsv [--dry-run] [--lang en]
    python tools/vocab.py add [--lang en]
    python tools/vocab.py search TEXT [--limit 20]
    python tools/vocab.py list [--topic TOPIC] [--limit 30]
    python tools/vocab.py stats
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
import os
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

#!/usr/bin/env python3
"""meetily_reader.py: pull a finished Meetily Community meeting into Axiom's discovery format.

Reads Meetily's local SQLite database through one coherent read-only snapshot (SQLite backup API,
never a file-by-file copy of the database and its WAL) and writes, per meeting:
  transcript.md   time-stamped transcript with the source of each line (mic = us, system = them)
  extraction.md   process map, volumes, tools, pain list, next steps and candidate agent tasks,
                  each item paired with a CANDIDATE quote: the closest transcript sentence(s) by
                  word overlap that is not a bare question and that contains every number the item
                  states. A candidate quote is a lexical match, not proof. Check every item.
  extraction.json same content, machine readable

Python 3.10+, standard library only.

  python3 meetily_reader.py --list
  python3 meetily_reader.py --meeting "<id or part of the title>" --out ./out
"""
import argparse, atexit, json, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path

DEFAULT_DB = Path.home() / "Library/Application Support/com.meetily.ai/meeting_minutes.sqlite"
STOP = set("""a an the and or but if of to in on at for with by from is are was were be been it its
this that these those we you they he she i our your their my me us them do does did so as not no
just about into then than there here what when who how all any each can will would could should
have has had get gets got one up out over per like really very""".split())
# Repetitive, rules-following work an operational agent could own (matched on word starts).
TASK_CUES = re.compile(r"\b(call(s|ing)? back|callback|follow(s|ing)?[ -]?up|schedul|remind|enter(s|ed|ing)?\b|"
                       r"status|update|messag|email|text(s|ed|ing)?\b|book(s|ed|ing)?\b|intake|triag|approv|"
                       r"clos(e|ed|es|ing)\b|assign|respon|confirm|log(s|ged|ging)?\b|track)", re.I)
SPEAKER = {"mic": "Us (mic)", "system": "Them (system)"}
CANDIDATE_NOTE = ("A candidate quote is the closest transcript sentence(s) by word overlap that is not a bare "
                  "question and contains every number the item states. It is not proof: check every item "
                  "against its quote, and check every next-step owner (Meetily records no speaker).")


# ---------- database ----------

def _quiescent_copy(db: Path, tmp: Path, tries: int = 3) -> Path:
    """Copy a database that has no -wal/-shm (Meetily closed) and prove it did not change meanwhile."""
    wal, shm = Path(str(db) + "-wal"), Path(str(db) + "-shm")
    for _ in range(tries):
        if wal.exists() or shm.exists():
            break
        before = os.stat(db)
        dst = tmp / "quiescent.sqlite"
        shutil.copy2(db, dst)
        after = os.stat(db)
        if (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns) \
                and not wal.exists() and not shm.exists():
            return dst
    sys.exit("Meetily's database changed while it was being read. Try again, or quit Meetily first.")


def open_copy(db: Path, pages: int = -1, progress=None) -> sqlite3.Connection:
    """Return a read-only connection to one coherent snapshot of the Meetily database.

    While Meetily runs, the source is opened in SQLite's read-only mode and copied with the backup
    API. Backup reads pages under SQLite's own locking and restarts if another connection commits
    mid-copy, so the snapshot is always a state that really existed. When Meetily is closed, a
    WAL-mode file with no -shm cannot be opened read-only, so the single main file is copied and
    checked unchanged before and after. The original database is never opened for writing.
    `pages` / `progress` pass through to Connection.backup (the tests use them to interleave a writer)."""
    if not db.exists():
        sys.exit(f"Meetily database not found: {db}")
    tmp = Path(tempfile.mkdtemp(prefix="meetily-read-"))
    atexit.register(shutil.rmtree, tmp, True)
    try:
        src = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        src.execute("select count(*) from sqlite_master").fetchone()
    except sqlite3.OperationalError:
        src = sqlite3.connect(_quiescent_copy(db, tmp))  # a private temp copy; the source is untouched
    snap = tmp / "snapshot.sqlite"
    out = sqlite3.connect(snap)
    try:
        src.backup(out, pages=pages, progress=progress)
    finally:
        src.close()
    out.execute("pragma journal_mode=delete")  # the snapshot then opens read-only with no sidecar files
    out.close()
    con = sqlite3.connect(f"{snap.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def list_meetings(con):
    q = """select m.id, m.title, m.created_at, m.folder_path,
                  (select count(*) from transcripts t where t.meeting_id = m.id) as segs,
                  (select status from summary_processes s where s.meeting_id = m.id) as summary
           from meetings m order by m.created_at"""
    return [dict(r) for r in con.execute(q)]


def find_meeting(con, key):
    rows = list_meetings(con)
    exact = [r for r in rows if r["id"] == key]
    if exact:
        return exact[0]
    hits = [r for r in rows if key.lower() in (r["title"] or "").lower()]
    if len(hits) != 1:
        sys.exit(f"'{key}' matched {len(hits)} meetings; use --list and pass the id")
    return hits[0]


def segments(con, mid):
    rows = con.execute("""select transcript, timestamp, audio_start_time, audio_end_time, speaker
                          from transcripts where meeting_id = ?
                          order by coalesce(audio_start_time, 0), timestamp""", (mid,)).fetchall()
    return [{"text": r["transcript"].strip(), "start": r["audio_start_time"], "end": r["audio_end_time"],
             "speaker": r["speaker"], "wallclock": r["timestamp"]} for r in rows if r["transcript"].strip()]


def summary_markdown(con, mid):
    r = con.execute("select status, result from summary_processes where meeting_id = ?", (mid,)).fetchone()
    if not r or not r["result"]:
        return None, (r["status"] if r else None)
    try:
        data = json.loads(r["result"])
        md = data.get("markdown") if isinstance(data, dict) else None
    except json.JSONDecodeError:
        md = r["result"]
    return md, r["status"]


# ---------- parsing the summary ----------

def parse_sections(md: str) -> dict:
    """Split summary markdown into {section title: [items]} (handles **Title**, # Title, tables, bullets)."""
    sections, cur = {}, "_preamble"
    for line in md.splitlines():
        s = line.strip()
        m = re.match(r"^(?:#{1,4}\s*(.+?)\s*#*$|\*\*(.+?)\*\*:?$)", s)
        if m:
            cur = (m.group(1) or m.group(2)).strip().strip("*").strip()
            sections.setdefault(cur, [])
            continue
        if not s or re.match(r"^\|?\s*:?-{2,}", s):
            continue
        if s.startswith("|"):
            cells = [c.strip().strip("*").strip() for c in s.strip("|").split("|")]
            if all(c.lower() in ("step", "who", "tool", "pain", "cost or impact", "owner", "action", "when",
                                 "deliverable", "due date", "concern", "impact", "") for c in cells):
                continue  # header row
            item = " | ".join(c for c in cells if c)
        else:
            item = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", s)
        if item:
            sections.setdefault(cur, []).append(item)
    return sections


def pick(sections, *keys):
    out = []
    for title, items in sections.items():
        if any(k in title.lower() for k in keys):
            out += items
    return out


# ---------- candidate quotes ----------

def stem(w):
    for suf in ("ing", "ed", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def toks(text):
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower().replace(",", "")) if w not in STOP]


def fmt_t(sec):
    if sec is None:
        return "--:--"
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
NUMWORDS = set(ONES[1:]) | set(TENS[2:]) | {"hundred", "thousand", "million", "half", "dozen"}


def num2words(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + num2words(n % 100))
    if n < 1_000_000:
        return num2words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + num2words(n % 1000))
    return num2words(n // 1_000_000) + " million" + ("" if n % 1_000_000 == 0 else " " + num2words(n % 1_000_000))


def number_words(text: str) -> set:
    """Every number word a text states, with digits spelled out ("$450" -> four, hundred, fifty)."""
    t = re.sub(r"\d[\d,]*", lambda m: " " + num2words(int(m.group(0).replace(",", "") or 0)) + " ", text.lower())
    t = re.sub(r"\ba (hundred|thousand|million)\b", r"one \1", t)  # "a hundred" == 100
    return {w for w in re.findall(r"[a-z]+", t) if w in NUMWORDS}


def item_numbers(item: str) -> set:
    """Numbers an extracted item asserts, from all of its cells. A cell that is only a step number is
    skipped, and a bare "one" is not checked ("one-page", "one lane" are wording, not quantities)."""
    cells = [c for c in item.replace("*", "").split(" | ") if not re.fullmatch(r"\s*\d+[.)]?\s*", c)]
    return number_words(" ".join(cells)) - {"one"}


def sentences(segs):
    """Split segments into sentences; each sentence gets a time interpolated inside its segment."""
    out = []
    for s in segs:
        parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", s["text"]) if p.strip()]
        total = sum(len(p) for p in parts) or 1
        start, end = s["start"], s["end"]
        done = 0
        for p in parts:
            t = None if start is None else start + ((end or start) - start) * done / total
            out.append({"text": p, "start": t, "speaker": s["speaker"], "question": p.endswith("?")})
            done += len(p)
    return out


def link_quote(item, segs, min_score=0.34, sents=None):
    """Find a CANDIDATE quote for an extracted item: the best 1 to 3 consecutive transcript sentences.

    Word match: table rows are matched on their first cell (the step or pain itself). A span needs
    >= min_score of the item's content words, or >= 4 of them for long paraphrased items.
    Checks: a span made only of questions is never used, and every number stated anywhere in the
    item (all cells) must appear in the span. If no word-matching span holds all the numbers, the
    closest one is returned with status "numbers_missing" and the missing numbers, so the item is
    flagged for a human. Even status "candidate" is only a word match, not proof."""
    first = item.split(" | ")[0].replace("*", "")
    want = set(toks(first)) or set(toks(item))
    if not want:
        return None
    need = item_numbers(item)
    sents = sents if sents is not None else sentences(segs)
    best = best_ok = None  # (score, start index, span)
    for i in range(len(sents)):
        for span in (1, 2, 3):
            if i + span > len(sents):
                continue
            chunk = sents[i:i + span]
            if all(s["question"] for s in chunk):
                continue  # a question is not evidence for its own answer
            text = " ".join(s["text"] for s in chunk)
            hit = want & set(toks(text))
            score = (len(hit) + sum(1 for w in hit if w.isdigit())) / (len(want) + sum(1 for w in want if w.isdigit()))
            score -= 0.04 * (span - 1)  # prefer the shortest quote that carries the evidence
            if len(hit) >= 4:
                score = max(score, min_score)
            if score < min_score:
                continue
            if best is None or score > best[0]:
                best = (score, i, span)
            if need <= number_words(text) and (best_ok is None or score > best_ok[0]):
                best_ok = (score, i, span)
    chosen, status = (best_ok, "candidate") if best_ok else (best, "numbers_missing")
    if chosen is None:
        return None
    score, i, span = chosen
    seg = sents[i:i + span]
    quote = " ".join(s["text"] for s in seg)
    return {"t": fmt_t(seg[0]["start"]), "speaker": seg[0]["speaker"], "score": round(score, 2),
            "status": status, "numbers_missing": sorted(need - number_words(quote)), "quote": quote}


def build(meeting, segs, md):
    secs = parse_sections(md) if md else {}
    groups = {
        "process_map": pick(secs, "workflow", "process"),
        "volumes": pick(secs, "volume", "timing"),
        "tools": pick(secs, "tool", "system"),
        "pains": pick(secs, "pain", "risk", "concern"),
        "outcome": pick(secs, "outcome", "goal", "success"),
        "decision_makers": pick(secs, "decision"),
        "next_steps": pick(secs, "next step", "action"),
    }
    out = {"meeting": {k: meeting[k] for k in ("id", "title", "created_at")}, "summary_present": bool(md)}
    sents = sentences(segs)
    for g, items in groups.items():
        # next-step rows start with the owner; match on the action instead
        key = (lambda it: it.split(" | ", 1)[-1]) if g == "next_steps" else (lambda it: it)
        out[g] = [{"item": it, "evidence": link_quote(key(it), segs, sents=sents)} for it in items]
    tasks = []
    for src in ("pains", "process_map"):
        for row in out[src]:
            first = row["item"].split(" | ")[0]
            if first.lower().startswith("customer"):
                continue  # what the customer does is the trigger, not the work
            ok = bool(row["evidence"]) and row["evidence"]["status"] == "candidate"
            if TASK_CUES.search(row["item"]) and ok and first not in {t["task"][22:] for t in tasks}:
                tasks.append({"task": "Candidate agent task: " + row["item"].split(" | ")[0],
                              "from": src, "evidence": row["evidence"]})
    out["candidate_agent_tasks"] = tasks
    allrows = [r for g in groups for r in out[g]]
    out["stats"] = {
        "items": len(allrows),
        "items_with_candidate_quote": sum(1 for r in allrows if r["evidence"] and r["evidence"]["status"] == "candidate"),
        "items_numbers_missing": [r["item"] for r in allrows if r["evidence"] and r["evidence"]["status"] == "numbers_missing"],
        "items_without_quote": [r["item"] for r in allrows if not r["evidence"]],
        "note": CANDIDATE_NOTE,
    }
    return out


# ---------- output ----------

def write_transcript(meeting, segs, path):
    lines = [f"# {meeting['title']}", "", f"Meetily meeting id `{meeting['id']}`, created {meeting['created_at']}.",
             "Source labels: mic = our side, system = the other side of the call. Community edition has no speaker names.", ""]
    for s in segs:
        lines.append(f"**[{fmt_t(s['start'])}] {SPEAKER.get(s['speaker'], s['speaker'] or 'unlabeled')}:** {s['text']}")
        lines.append("")
    path.write_text("\n".join(lines))


def write_extraction(x, path):
    def block(title, rows, key="item"):
        L = [f"## {title}", ""]
        if not rows:
            return L + ["_Nothing extracted._", ""]
        for n, r in enumerate(rows, 1):
            ev = r["evidence"]
            L.append(f"{n}. {r[key]}")
            who = SPEAKER.get(ev["speaker"], ev["speaker"] or "") if ev else ""
            if ev and ev["status"] == "candidate":
                L.append(f"   > Candidate quote, verify. [{ev['t']}] {who}: \"{ev['quote']}\" (word match {ev['score']})")
            elif ev:
                L.append(f"   > NUMBERS NOT IN QUOTE ({', '.join(ev['numbers_missing'])}). Closest words "
                         f"[{ev['t']}]: \"{ev['quote']}\". Check this item by hand.")
            else:
                L.append("   > NO CANDIDATE QUOTE FOUND. Check this item by hand before using it.")
        return L + [""]
    st = x["stats"]
    L = [f"# Discovery extraction: {x['meeting']['title']}", "",
         f"Items: {st['items']}. Candidate quote found: {st['items_with_candidate_quote']}. "
         f"Numbers not in quote: {len(st['items_numbers_missing'])}. No quote: {len(st['items_without_quote'])}.", "",
         CANDIDATE_NOTE, ""]
    if not x["summary_present"]:
        L += ["_No Meetily summary yet. Generate one with the Axiom Discovery template, then re-run._", ""]
    L += block("Process map (as described)", x["process_map"])
    L += block("Volumes and timing", x["volumes"])
    L += block("Tools and systems", x["tools"])
    L += block("Pain list", x["pains"])
    L += block("Desired outcome", x["outcome"])
    L += block("Decision makers", x["decision_makers"])
    L += block("Next steps", x["next_steps"])
    L += block("Candidate agent tasks (for Axiom to judge; one lane per engagement)", x["candidate_agent_tasks"], key="task")
    path.write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--meeting")
    ap.add_argument("--out", type=Path, default=Path("out"))
    a = ap.parse_args()
    con = open_copy(a.db)
    if a.list or not a.meeting:
        for r in list_meetings(con):
            print(f"{r['id']}  {r['created_at'][:19]}  segs={r['segs']:<4} summary={r['summary']}  {r['title']}")
        return
    m = find_meeting(con, a.meeting)
    segs = segments(con, m["id"])
    md, status = summary_markdown(con, m["id"])
    d = a.out / re.sub(r"[^A-Za-z0-9_.-]+", "-", m["title"]).strip("-")
    d.mkdir(parents=True, exist_ok=True)
    write_transcript(m, segs, d / "transcript.md")
    x = build(m, segs, md)
    x["summary_status"] = status
    x["summary_markdown"] = md
    (d / "extraction.json").write_text(json.dumps(x, indent=1))
    write_extraction(x, d / "extraction.md")
    st = x["stats"]
    print(f"wrote {d}/transcript.md, extraction.md, extraction.json ({len(segs)} segments; "
          f"candidate quote for {st['items_with_candidate_quote']}/{st['items']} items, "
          f"{len(st['items_numbers_missing'])} with numbers not in the quote, {len(st['items_without_quote'])} with none)")


if __name__ == "__main__":
    main()

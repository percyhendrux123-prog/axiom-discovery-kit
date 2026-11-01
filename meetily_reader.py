#!/usr/bin/env python3
"""meetily_reader.py: pull a finished Meetily Community meeting into Axiom's discovery format.

Reads Meetily's local SQLite database (a temporary copy, so the running app is never locked
or written to) and writes, per meeting:
  transcript.md   time-stamped transcript with the source of each line (mic = us, system = them)
  extraction.md   process map, volumes, tools, pain list, next steps and candidate agent tasks,
                  each item linked to the closest transcript quote with its timestamp
  extraction.json same content, machine readable

Python 3.10+, standard library only.

  python3 meetily_reader.py --list
  python3 meetily_reader.py --meeting "<id or part of the title>" --out ./out
"""
import argparse, atexit, json, re, shutil, sqlite3, sys, tempfile
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


# ---------- database ----------

def open_copy(db: Path) -> sqlite3.Connection:
    """Copy the DB (+WAL/SHM) to a temp dir and open the copy read-only."""
    if not db.exists():
        sys.exit(f"Meetily database not found: {db}")
    tmp = Path(tempfile.mkdtemp(prefix="meetily-read-"))
    atexit.register(shutil.rmtree, tmp, True)
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db) + suffix)
        if src.exists():
            shutil.copy2(src, tmp / (db.name + suffix))
    con = sqlite3.connect(tmp / db.name)
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


# ---------- quote linking ----------

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
            out.append({"text": p, "start": t, "speaker": s["speaker"]})
            done += len(p)
    return out


def link_quote(item, segs, min_score=0.34, sents=None):
    """Closest 1-3 consecutive transcript sentences for an extracted item, by content-word overlap.

    Table rows are matched on their first cell (the step / pain itself), since later cells are the
    model's own commentary. A link needs >= min_score of the item's content words, or >= 4 of them
    for long paraphrased items."""
    first = item.split(" | ")[0].replace("*", "")
    want = set(toks(first)) or set(toks(item))
    if not want:
        return None
    sents = sents if sents is not None else sentences(segs)
    best, best_i, best_span = 0.0, None, 1
    for i in range(len(sents)):
        for span in (1, 2, 3):
            if i + span > len(sents):
                continue
            have = set(toks(" ".join(s["text"] for s in sents[i:i + span])))
            hit = want & have
            score = (len(hit) + sum(1 for w in hit if w.isdigit())) / (len(want) + sum(1 for w in want if w.isdigit()))
            score -= 0.04 * (span - 1)  # prefer the shortest quote that carries the evidence
            if len(hit) >= 4:
                score = max(score, min_score)
            if score > best:
                best, best_i, best_span = score, i, span
    if best_i is None or best < min_score:
        return None
    seg = sents[best_i:best_i + best_span]
    return {"t": fmt_t(seg[0]["start"]), "speaker": seg[0]["speaker"], "score": round(best, 2),
            "quote": " ".join(s["text"] for s in seg)}


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
            if TASK_CUES.search(row["item"]) and row["evidence"] and first not in {t["task"][22:] for t in tasks}:
                tasks.append({"task": "Candidate agent task: " + row["item"].split(" | ")[0],
                              "from": src, "evidence": row["evidence"]})
    out["candidate_agent_tasks"] = tasks
    allrows = [r for g in groups for r in out[g]]
    out["stats"] = {"items": len(allrows), "items_with_quote": sum(1 for r in allrows if r["evidence"]),
                    "items_without_quote": [r["item"] for r in allrows if not r["evidence"]]}
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
            if ev:
                L.append(f"   > [{ev['t']}] {SPEAKER.get(ev['speaker'], ev['speaker'] or '')}: \"{ev['quote']}\" (match {ev['score']})")
            else:
                L.append("   > NO SUPPORTING QUOTE FOUND. Check this item by hand before using it.")
        return L + [""]
    L = [f"# Discovery extraction: {x['meeting']['title']}", "",
         f"Items: {x['stats']['items']}, linked to a quote: {x['stats']['items_with_quote']}.", ""]
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
    print(f"wrote {d}/transcript.md, extraction.md, extraction.json "
          f"({len(segs)} segments; {x['stats']['items_with_quote']}/{x['stats']['items']} items linked to a quote)")


if __name__ == "__main__":
    main()

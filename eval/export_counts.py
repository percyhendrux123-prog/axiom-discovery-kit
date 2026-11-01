#!/usr/bin/env python3
"""export_counts.py: per-meeting segment and speaker-label counts from the Meetily database.

Writes eval/results/segment-counts.json (every meeting in the database: id, title, creation time,
segments, segments with an empty speaker field, distinct speaker values) and a plain-text transcript
export for any meeting not already in eval/results/transcripts-raw/. All meetings in the eval
database are synthetic test calls; run it only on a database that holds nothing else.

  python3 eval/export_counts.py [--db <path>]
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import meetily_reader as mr  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", type=Path, default=mr.DEFAULT_DB)
ap.add_argument("--names", type=Path, default=HERE / "meetings.json", help="run name -> meeting id")
a = ap.parse_args()

names = {v["meeting_id"]: k for k, v in json.loads(a.names.read_text()).items()}
con = mr.open_copy(a.db)
rows, raw_dir = [], HERE / "results" / "transcripts-raw"
for m in mr.list_meetings(con):
    r = con.execute("""select count(*) n, sum(speaker is null or trim(speaker) = '') empty,
                              group_concat(distinct speaker) vals
                       from transcripts where meeting_id = ?""", (m["id"],)).fetchone()
    name = names.get(m["id"], m["title"])
    rows.append({"run": name, "meeting_id": m["id"], "title": m["title"], "created_at": m["created_at"],
                 "segments": r["n"], "speaker_empty": r["empty"] or 0, "speaker_values": r["vals"]})
    out = raw_dir / f"{name}.txt"
    if name in names.values() and not out.exists():
        out.write_text("\n".join(s["text"] for s in mr.segments(con, m["id"])) + "\n")
total = {"meetings": len(rows), "segments": sum(r["segments"] for r in rows),
         "speaker_empty": sum(r["speaker_empty"] for r in rows)}
(HERE / "results" / "segment-counts.json").write_text(json.dumps({"total": total, "meetings": rows}, indent=1) + "\n")
for r in rows:
    print(f"{r['run']:<28} segments {r['segments']:>3}  speaker empty {r['speaker_empty']:>3}")
print("total", total)

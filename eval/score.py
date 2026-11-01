#!/usr/bin/env python3
"""score.py: score Meetily output against the synthetic discovery-call scripts.

  python3 score.py --call call1-hvac --meeting "<meeting id or title part>" --method import \
                   [--timeline ../audio/call1-hvac/timeline.json] [--expect-source system] --out scores/

Measures
  1. WER of the Meetily transcript vs the script (both normalised by textnorm.normalise).
  2. Source split: share of transcript segments labelled mic / system / unlabelled, against what
     the feed method should produce (--expect-source), when the method can produce a split.
  3. Summary checklist: each item in checklists.json counted as captured yes/no in the summary.
Standard library only. Reads a temporary copy of the Meetily database.
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from textnorm import normalise, wer, script_reference  # noqa: E402
import meetily_reader as mr  # noqa: E402


def check_items(summary_md: str, items: list) -> list:
    norm = " ".join(normalise(summary_md or ""))
    squashed = norm.replace(" ", "")
    out = []
    for it in items:
        groups = []
        for alts in it["all"]:
            hit = next((a for a in alts if " ".join(normalise(a)) in norm or a.replace(" ", "") in squashed), None)
            groups.append(hit)
        out.append({"id": it["id"], "cat": it["cat"], "item": it["item"],
                    "captured": all(g is not None for g in groups), "matched": groups})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--call", required=True)
    ap.add_argument("--meeting", required=True)
    ap.add_argument("--method", required=True, help="import | live-system-audio")
    ap.add_argument("--db", type=Path, default=mr.DEFAULT_DB)
    ap.add_argument("--scripts", type=Path, default=HERE / "scripts")
    ap.add_argument("--expect-source", default=None, help="system | mic | none (import has no split)")
    ap.add_argument("--summary-model", default="")
    ap.add_argument("--out", type=Path, default=HERE / "results" / "scores")
    a = ap.parse_args()

    con = mr.open_copy(a.db)
    m = mr.find_meeting(con, a.meeting)
    segs = mr.segments(con, m["id"])
    md, status = mr.summary_markdown(con, m["id"])
    lines, ref_text = script_reference(a.scripts / f"{a.call}.txt")
    hyp_text = " ".join(s["text"] for s in segs)
    w = wer(normalise(ref_text), normalise(hyp_text))

    labels = {}
    for s in segs:
        labels[s["speaker"] or "unlabelled"] = labels.get(s["speaker"] or "unlabelled", 0) + 1
    split = {"segments": len(segs), "labels": labels, "expected": a.expect_source}
    if a.expect_source in ("mic", "system"):
        split["share_expected"] = round(labels.get(a.expect_source, 0) / max(len(segs), 1), 3)

    checklist = json.loads((HERE / "checklists.json").read_text())[a.call]
    checks = check_items(md, checklist)
    by_cat = {}
    for c in checks:
        d = by_cat.setdefault(c["cat"], [0, 0]); d[1] += 1; d[0] += c["captured"]
    x = mr.build(m, segs, md)
    res = {"call": a.call, "method": a.method, "meeting_id": m["id"], "meeting_title": m["title"],
           "summary_model": a.summary_model, "summary_status": status,
           "wer": w, "source_split": split,
           "summary_checklist": {"captured": sum(c["captured"] for c in checks), "total": len(checks),
                                 "by_category": {k: f"{v[0]}/{v[1]}" for k, v in by_cat.items()},
                                 "items": checks},
           "quote_linking": x["stats"]}
    a.out.mkdir(parents=True, exist_ok=True)
    tag = f"{a.call}--{a.method}" + (f"--{a.summary_model}" if a.summary_model else "")
    (a.out / f"{tag}.json").write_text(json.dumps(res, indent=1))
    print(f"{tag}: WER {w['wer']:.1%} (S{w['sub']} D{w['del']} I{w['ins']} / {w['ref_words']} ref words); "
          f"segments {len(segs)} labels {labels}; checklist {res['summary_checklist']['captured']}/{len(checks)} "
          f"{res['summary_checklist']['by_category']}; quotes {x['stats']['items_with_quote']}/{x['stats']['items']}")


if __name__ == "__main__":
    main()

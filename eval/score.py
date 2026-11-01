#!/usr/bin/env python3
"""score.py: score Meetily output against the synthetic discovery-call scripts.

  python3 score.py --call call1-hvac --meeting "<meeting id or title part>" --method import \
                   [--timeline ../audio/call1-hvac/timeline.json] [--expect-source system] --out scores/

Measures
  1. WER of the Meetily transcript vs the script (both normalised by textnorm.normalise).
  2. Source split: share of transcript segments labelled mic / system / unlabelled, against what
     the feed method should produce (--expect-source), when the method can produce a split.
  3. Summary keyword checklist: each item in checklists.json counted as a keyword hit yes/no in the
     summary (whole words, same summary line, not negated). A keyword hit is not factual accuracy.
Standard library only. Reads one coherent read-only snapshot of the Meetily database.
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from textnorm import normalise, wer, script_reference  # noqa: E402
import meetily_reader as mr  # noqa: E402


NEGATORS = {"not", "no", "never", "without", "none", "nor", "neither", "dont", "doesnt", "didnt", "isnt",
            "arent", "wasnt", "werent", "wont", "cant", "cannot", "lacks", "lack"}
SUFFIXES = ("", "s", "es", "d", "ed", "ing")  # "message" also hits "messages"; "eight" never hits "freight"


def _phrase_at(tokens, phrase, i, prefix=False):
    n = len(phrase)
    if i + n > len(tokens) or tokens[i:i + n - 1] != phrase[:-1]:
        return False
    last = tokens[i + n - 1]
    if prefix:
        return last.startswith(phrase[-1])
    return any(last == phrase[-1] + s for s in SUFFIXES)


def _hit(tokens, alt):
    """True when alt occurs in tokens as whole words and is not negated in the 4 words before it.

    An alternative ending in '*' is an explicit word-start prefix ("estimat*" hits "estimate",
    "estimator"); every other alternative must match whole words (plural/tense endings allowed)."""
    prefix = alt.endswith("*")
    alt = alt.rstrip("*")
    for phrase in {tuple(normalise(alt)), (alt.replace(" ", "").lower(),)}:
        phrase = list(phrase)
        if not phrase or not phrase[0]:
            continue
        for i in range(len(tokens)):
            if _phrase_at(tokens, phrase, i, prefix) and not NEGATORS & set(tokens[max(0, i - 4):i]):
                return True
    return False


def check_items(summary_md: str, items: list) -> list:
    """Automatic KEYWORD-checklist hits, not a factual-accuracy score.

    An item is a hit when every group in its 'all' list has an alternative that appears in the SAME
    summary line (a bullet, table row or paragraph), as whole words (plural/tense endings allowed),
    and not after a negation ("not", "no", "never", "without", "don't" ...) in the 4 words before it.
    It does not check amounts, owners or deadlines; the hand audit does that."""
    lines = [normalise(l) for l in (summary_md or "").splitlines()]
    lines = [l for l in lines if l]
    out = []
    for it in items:
        found = None
        for toks in lines:
            groups = [next((a for a in alts if _hit(toks, a)), None) for alts in it["all"]]
            if all(g is not None for g in groups):
                found = groups
                break
        out.append({"id": it["id"], "cat": it["cat"], "item": it["item"],
                    "captured": found is not None, "matched": found})
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
           "summary_checklist": {"metric": "automatic keyword-checklist hits (not factual accuracy)",
                                 "captured": sum(c["captured"] for c in checks), "total": len(checks),
                                 "by_category": {k: f"{v[0]}/{v[1]}" for k, v in by_cat.items()},
                                 "items": checks},
           "quote_linking": x["stats"]}
    a.out.mkdir(parents=True, exist_ok=True)
    tag = f"{a.call}--{a.method}" + (f"--{a.summary_model}" if a.summary_model else "")
    (a.out / f"{tag}.json").write_text(json.dumps(res, indent=1))
    print(f"{tag}: WER {w['wer']:.1%} (S{w['sub']} D{w['del']} I{w['ins']} / {w['ref_words']} ref words); "
          f"segments {len(segs)} labels {labels}; keyword hits {res['summary_checklist']['captured']}/{len(checks)} "
          f"{res['summary_checklist']['by_category']}; candidate quotes {x['stats']['items_with_candidate_quote']}/{x['stats']['items']}")


if __name__ == "__main__":
    main()

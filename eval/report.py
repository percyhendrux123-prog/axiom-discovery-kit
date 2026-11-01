#!/usr/bin/env python3
"""report.py: build the results table from eval/results/scores/*.json and hand-audit.json.

  python3 eval/report.py            # prints markdown, writes eval/results/results.md
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from score import check_items  # noqa: E402

R = HERE / "results"
audit = json.loads((R / "hand-audit.json").read_text())
checklists = json.loads((HERE / "checklists.json").read_text())

rows = []
for f in sorted((R / "scores").glob("*.json")):
    d = json.loads(f.read_text())
    cond = d["method"].replace("import-", "").replace("live-system-audio", "live (system audio)")
    key = f"{d['call']}-{d['method'].replace('import-', '')}" if d["method"].startswith("import") else f"{d['call']}-live"
    a = audit.get(key, {})
    w = d["wer"]
    rows.append({
        "call": d["call"], "condition": cond,
        "feed": "import" if d["method"].startswith("import") else "played through system audio while recording",
        "wer": w["wer"], "sub": w["sub"], "del": w["del"], "ins": w["ins"], "ref_words": w["ref_words"],
        "segments": d["source_split"]["segments"], "labels": d["source_split"]["labels"],
        "checklist": f"{d['summary_checklist']['captured']}/{d['summary_checklist']['total']}",
        "by_category": d["summary_checklist"]["by_category"],
        "quotes": f"{d['quote_linking']['items_with_quote']}/{d['quote_linking']['items']}",
        "factual_errors": len(a.get("factual_errors", [])), "owner_errors": len(a.get("owner_errors", [])),
        "missed_by_hand": len(a.get("missed", [])),
    })

# smallest built-in model (Gemma 3 1B) on call 1, from the saved Meetily result JSON
gemma = []
for tag, fn in [("Axiom Discovery template", "call1-gemma1b-axiomtemplate.result.json"),
                ("bundled Client / Sales template", "call1-gemma1b-salestemplate.result.json")]:
    p = R / "meetily-out" / fn
    if p.exists():
        md = json.loads(p.read_text())["markdown"]
        c = check_items(md, checklists["call1-hvac"])
        gemma.append((tag, sum(x["captured"] for x in c), len(c)))

L = ["| Call | Condition | How it was fed | WER | Sub / Del / Ins | Source labels | Checklist (auto) | Items linked to a quote | Factual errors (hand) | Wrong or vague owners (hand) |",
     "|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    lab = ", ".join(f"{k} {v}" for k, v in r["labels"].items())
    L.append(f"| {r['call']} | {r['condition']} | {r['feed']} | {r['wer']:.1%} | {r['sub']} / {r['del']} / {r['ins']} of {r['ref_words']} | {lab} | {r['checklist']} | {r['quotes']} | {r['factual_errors']} | {r['owner_errors']} |")
L.append("")
L.append("Summaries above: Qwen 3.5 4B (built-in, local) with the Axiom Discovery template.")
L.append("")
if gemma:
    L.append("| Smallest built-in model, Gemma 3 1B, call 1 | Checklist (auto) |")
    L.append("|---|---|")
    for tag, n, t in gemma:
        L.append(f"| {tag} | {n}/{t} |")
md = "\n".join(L)
(R / "results.md").write_text(md + "\n")
(R / "results.json").write_text(json.dumps({"rows": rows, "gemma3_1b": gemma}, indent=1))
print(md)

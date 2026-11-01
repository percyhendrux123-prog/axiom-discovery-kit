#!/bin/bash
# rescore_all.sh: re-run score.py and meetily_reader.py on every scored run in eval/meetings.json,
# then rebuild the results table. Needs the eval meetings in the local Meetily database.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf eval/results/scores eval/results/extractions
python3 - <<'EOF' | while read -r run call method expect mid; do
import json
for run, v in json.load(open("eval/meetings.json")).items():
    if "call" in v:
        print(run, v["call"], v["method"], v.get("expect_source", "none"), v["meeting_id"])
EOF
  args=(--call "$call" --meeting "$mid" --method "$method" --summary-model qwen3.5-4b)
  [ "$expect" != none ] && args+=(--expect-source "$expect")
  python3 eval/score.py "${args[@]}"
  python3 meetily_reader.py --meeting "$mid" --out "eval/results/extractions/$run" >/dev/null
done
python3 eval/report.py >/dev/null
echo "rebuilt eval/results/results.md"

#!/usr/bin/env python3
"""werdiff.py: show where the transcript differs from the script (runs of deleted / inserted / substituted words).

  python3 werdiff.py <script.txt> <hypothesis.txt>
"""
import difflib, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from textnorm import normalise, script_reference  # noqa: E402

_, ref = script_reference(sys.argv[1])
hyp = Path(sys.argv[2]).read_text()
r, h = normalise(ref), normalise(hyp)
sm = difflib.SequenceMatcher(a=r, b=h, autojunk=False)
for op, a0, a1, b0, b1 in sm.get_opcodes():
    if op == "equal":
        continue
    ctx = " ".join(r[max(0, a0 - 4):a0])
    print(f"{op:8s} @{a0:4d} ...{ctx} [ref: {' '.join(r[a0:a1])}] [hyp: {' '.join(h[b0:b1])}]")

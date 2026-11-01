"""Text normalisation and word error rate, shared by the eval harness.

Both the reference script and the Meetily transcript go through the same
normalise() so number formatting ("35" vs "thirty five") is not counted as an error.
"""
import re

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
NUMWORDS = set(ONES) | set(TENS) | {"hundred", "thousand", "million"}


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


def _digits(m):
    s = m.group(0).replace(",", "")
    try:
        return " " + num2words(int(s)) + " "
    except ValueError:
        return " " + s + " "


SAME = {"okay": "ok", "alright": "all right", "e-mail": "email", "percent": "percent"}
# Spacing-only variants of product names and compounds. Joined on both sides so
# "Job Nimbus" vs "JobNimbus" is not counted as a recognition error.
COMPOUNDS = ["job nimbus", "app folio", "service titan", "ring central", "company cam", "quick books",
             "white board", "call back", "hail storm", "google sheets"]


def normalise(text: str) -> list[str]:
    t = text.lower()
    t = re.sub(r"\be[-‐]mail", "email", t)  # before hyphens become spaces
    t = re.sub(r"\$(\d[\d,]*)", r"\1 dollars", t)
    t = t.replace("%", " percent")
    t = re.sub(r"(\d+):(\d\d)", lambda m: f"{m.group(1)} {m.group(2) if m.group(2) != '00' else ''}", t)
    t = re.sub(r"\d[\d,]*", _digits, t)
    t = re.sub(r"(?<=s)['’]s\b", "", t)  # Carlos's -> Carlos (ASR often drops it)
    t = t.replace("’", "'").replace("-", " ")
    t = re.sub(r"[^a-z' ]+", " ", t)
    t = t.replace("'", "")  # don't -> dont on both sides
    for k, v in SAME.items():
        t = re.sub(rf"\b{k}\b", v, t)
    for c in COMPOUNDS:
        t = re.sub(rf"\b{c}\b", c.replace(" ", ""), t)
    words = t.split()
    out = []
    for i, w in enumerate(words):
        # "a hundred" -> "one hundred"; drop "and" inside spoken numbers
        if w == "a" and i + 1 < len(words) and words[i + 1] in ("hundred", "thousand"):
            w = "one"
        if w == "and" and out and out[-1] in NUMWORDS and i + 1 < len(words) and words[i + 1] in NUMWORDS:
            continue
        out.append(w)
    return out


def wer(ref: list[str], hyp: list[str]) -> dict:
    """Levenshtein alignment at word level. Returns counts and rate."""
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    ops = [[None] * (m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        ops[0][j] = "I"
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        ops[i][0] = "D"
        r = ref[i - 1]
        for j in range(1, m + 1):
            if r == hyp[j - 1]:
                cur[j], ops[i][j] = prev[j - 1], "M"
            else:
                s, d, ins = prev[j - 1] + 1, prev[j] + 1, cur[j - 1] + 1
                best = min(s, d, ins)
                cur[j] = best
                ops[i][j] = "S" if best == s else ("D" if best == d else "I")
        prev = cur
    # backtrace for counts
    i, j, S, D, I = n, m, 0, 0, 0
    while i > 0 or j > 0:
        o = ops[i][j]
        if o == "M":
            i, j = i - 1, j - 1
        elif o == "S":
            S += 1; i, j = i - 1, j - 1
        elif o == "D":
            D += 1; i -= 1
        else:
            I += 1; j -= 1
    return {"ref_words": n, "hyp_words": m, "sub": S, "del": D, "ins": I,
            "wer": round((S + D + I) / max(n, 1), 4)}


def script_reference(path) -> tuple[list[dict], str]:
    lines = []
    for raw in open(path):
        if raw.startswith(("A: ", "P: ")):
            lines.append({"spk": raw[0], "text": raw[3:].strip()})
    return lines, " ".join(l["text"] for l in lines)

| Call | Condition | How it was fed | WER | Sub / Del / Ins | Source labels | Keyword-checklist hits (auto) | Candidate quote found | Numbers not in quote | No quote | Factual errors (hand) | Wrong or vague owners (hand) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| call1-hvac | clean | import | 1.0% | 4 / 5 / 3 of 1157 | unlabelled 15 | 21/23 | 31/34 | 3 | 0 | 1 | 2 |
| call1-hvac | live (system audio) | played through system audio while recording | 1.2% | 7 / 3 / 4 of 1157 | unlabelled 30 | 20/23 | 36/41 | 3 | 2 | 2 | 1 |
| call2-property | clean | import | 4.5% | 6 / 39 / 3 of 1076 | unlabelled 15 | 24/24 | 33/37 | 2 | 2 | 1 | 1 |
| call2-property | noise | import | 2.8% | 16 / 10 / 4 of 1076 | unlabelled 14 | 22/24 | 28/33 | 0 | 5 | 0 | 2 |
| call3-roofing | clean | import | 3.5% | 4 / 31 / 0 of 1006 | unlabelled 15 | 23/24 | 31/35 | 2 | 2 | 2 | 1 |
| call3-roofing | overlap | import | 13.6% | 18 / 117 / 2 of 1006 | unlabelled 14 | 20/24 | 25/30 | 2 | 3 | 2 | 1 |

Summaries above: Qwen 3.5 4B (built-in, local) with the Axiom Discovery template. Keyword-checklist hits are whole-word, same-line, non-negated keyword matches, not factual accuracy. A candidate quote is a word match that is not a bare question and contains every number the item states; it is not proof.

| Smallest built-in model, Gemma 3 1B, call 1 | Keyword-checklist hits (auto) |
|---|---|
| Axiom Discovery template | 0/23 |
| bundled Client / Sales template | 7/23 |

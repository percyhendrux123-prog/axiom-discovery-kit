# axiom-discovery-kit

A discovery-call kit for Meetily Community, the free, local, MIT-licensed meeting recorder for Mac. It includes an Axiom discovery template, a reader that turns a finished meeting into a process map, a pain list and candidate agent tasks, each item paired with a candidate quote from the transcript (unmatched items are flagged), and the eval we used to test it before using it on our own calls.

Axiom uses this on **its own** discovery calls. The audio and transcripts stay on the Mac and no cloud model is involved.

## What's in it

| Path | What it is |
|---|---|
| `templates/axiom_discovery.json` | Meetily summary template: company and people, workflow steps, volumes and timing, tools, pain points, desired outcome and measure, decision makers, next steps |
| `meetily_reader.py` | Reads one coherent, read-only snapshot of Meetily's local SQLite (SQLite backup API; it never writes the live file) and writes `transcript.md` plus `extraction.md`/`.json`. Each extracted item gets a **candidate quote**: the closest transcript sentence by word overlap that is not a bare question and contains every number the item states. Items whose numbers are not in the quote, or with no match, are flagged. A candidate quote is a word match, not proof. Standard library only. |
| `eval/` | The eval harness: synthetic call scripts (the ground truth), TTS render and mixing scripts, WER and keyword-checklist scoring, the hand audits, per-meeting segment counts, network-watch logs, and the results |
| `tests/` | Unit tests for the reader, the snapshot, the scorer and the text normaliser |

## Setup on a Mac

Requirements: Apple silicon, macOS 14.4 or later (Meetily's system-audio capture needs it), Python 3.10 or later.

1. Install **Meetily Community** from <https://github.com/Zackriya-Solutions/meetily/releases> (we tested 0.4.1) and open it.
2. Onboarding downloads Parakeet (about 670 MB) and Qwen 3.5 4B (about 2.6 GB). Keep **Qwen 3.5 4B** as the summary model. In our test the smallest model, Gemma 3 1B, failed (see results).
3. Allow the **Microphone** prompt. The **system audio** prompt only appears the first time you press record, so press record once and click Allow. Check System Settings > Privacy & Security > Screen & System Audio Recording > *System Audio Recording Only*.
4. Install the template:
   ```sh
   mkdir -p ~/Library/Application\ Support/Meetily/templates
   cp templates/axiom_discovery.json ~/Library/Application\ Support/Meetily/templates/
   ```
   Restart Meetily. In each meeting choose **Template > Axiom Discovery Call** before generating the summary, because new meetings default to Standard Meeting Notes.
5. After a call: generate the summary, then run
   ```sh
   python3 meetily_reader.py --list
   python3 meetily_reader.py --meeting <meeting-id> --out ./out
   ```
   Use the meeting id, not the title, because Meetily renames a meeting when it summarizes it.
6. Before anything goes into an agent design, check **every item against its candidate quote**, every item flagged `NUMBERS NOT IN QUOTE` or `NO CANDIDATE QUOTE FOUND`, and every **next-step owner**. If the transcript itself is wrong (cross-talk), the quote will agree with the wrong fact.

Leave every API-key field in Meetily empty. Everything above runs locally.

## Consent line (say it at the start of every call)

> "Before we start, I want to let you know this call is being recorded on my laptop so I can keep accurate notes. The recording stays with us and is not shared. Is that okay with you?"

Wait for a clear yes before you continue. Meetily joins no call as a bot, so nobody on the call can see it is recording. The spoken line is the notice, and it stays in the recording. Recording-consent law differs by state and country, and this line does not replace legal advice.

## Results (synthetic calls, Meetily Community 0.4.1, Mac mini M6 / 16 GB)

Three scripted discovery calls, 5.6 to 6.1 minutes each, voiced by two designed local TTS voices. Each call was run as a clean take, a noisy take (8 dB SNR) or a cross-talk take (12 overlapping turns). Summaries used Qwen 3.5 4B with the Axiom Discovery template. Full method, raw outputs and every caveat are in `eval/`.

| Call | Condition | Fed by | Word error | Keyword-checklist hits (auto) | Same, hand-checked | Candidate quote found | Wrong or vague next-step owners |
|---|---|---|---|---|---|---|---|
| HVAC intake | clean | import | 1.0% | 21/23 | 22/23 | 31/34 | 2 |
| HVAC intake | clean | live, via system audio | 1.2% | 20/23 | 23/23 | 36/41 | 1 |
| Property maintenance | clean | import | 4.5% | 24/24 | 24/24 | 33/37 | 1 |
| Property maintenance | noise | import | 2.8% | 22/24 | 22/24 | 28/33 | 2 |
| Roofing follow-up | clean | import | 3.5% | 23/24 | 24/24 | 31/35 | 1 |
| Roofing follow-up | overlap | import | 13.6% | 20/24 | 20/24 | 25/30 | 1 |

How to read it:
- **Keyword-checklist hits are not factual accuracy.** An item counts when its keywords appear as whole words on one summary line and are not negated. It does not check amounts, owners or deadlines. The hand-checked column re-reads every item the automatic rule changed its mind on (`eval/results/keyword-adjudication.json`). Owners and wrong facts come from a separate hand audit (`eval/results/hand-audit.json`).
- **A candidate quote is a word match, not proof.** 184 of 210 items got one. 12 had a number that was not in the closest quote, and 14 had no match. Every item still needs a human check against its quote.

What this shows and what it doesn't:
- Transcription is close to word for word on clear speech. **Cross-talk loses words.** In one case the transcript itself turned "three or four weeks" into "two years", and the summary repeated it. The candidate quote then agrees with the wrong fact, so quote matching cannot catch errors that are already in the transcript.
- Gemma 3 1B (the smallest built-in model) returned an empty outline with this template (0/23 keyword hits) and got 7 of 23 with Meetily's own sales template.
- **There is no "who said what"**: the speaker field was empty on all 120 segments in the 8 meetings we recorded or imported (`eval/results/segment-counts.json`, with a transcript export for each). That is why next-step owners need a human check.
- Import dropped three whole sentences that fell right before a chunk boundary in one file. The drops repeated exactly on a re-import.
- No internet connection was seen while recording, transcribing live, or summarizing. The watch polled `lsof` about every 1.3 s, which **misses short connections**: at app launch it saw nothing, while a 0.2 s poll caught two connections to GitHub (likely the update check). So this shows no long-lived traffic, not zero packets. The five file imports were not inside a watch window. Logs and windows: `eval/results/network/`.
- The calls are synthetic, voiced by designed TTS voices. They are not a test of real accents, phone-line audio or background voices, and we have not measured real calls.

## Running the eval

```sh
python3 -m unittest discover -s tests
python3 eval/score.py --call call1-hvac --meeting <meeting-id> --method import-clean --summary-model qwen3.5-4b
python3 eval/report.py         # REWRITES eval/results/results.md and results.json
eval/rescore_all.sh            # re-scores every run in eval/meetings.json (needs the eval meetings in Meetily)
python3 eval/export_counts.py  # per-meeting segment and speaker counts
```
Rendering new audio needs a local Qwen3-TTS VoiceDesign environment (`eval/render.py`, then `eval/assemble.py <call> clean|noise|overlap`). Audio files are not in this repo.

## Credit

This kit is built on **Meetily** by Zackriya Solutions, MIT License: <https://github.com/Zackriya-Solutions/meetily> ([license](https://github.com/Zackriya-Solutions/meetily/blob/main/LICENSE.md)). It is not a fork and not affiliated with or endorsed by them. Meetily does the recording, transcription and summary. This repo adds the template, the reader and the eval. Speech recognition is NVIDIA Parakeet as bundled by Meetily. The test voices came from Qwen3-TTS VoiceDesign, run locally.

## License

MIT. See `LICENSE`.

# axiom-discovery-kit

A discovery-call kit for Meetily Community, the free, local, MIT-licensed meeting recorder for Mac. It includes an Axiom discovery template, a reader that turns a finished meeting into a process map, a pain list and candidate agent tasks with every item linked to a quote, and the eval we used to test it before using it on our own calls.

Axiom uses this on **its own** discovery calls. The audio and transcripts stay on the Mac and no cloud model is involved.

## What's in it

| Path | What it is |
|---|---|
| `templates/axiom_discovery.json` | Meetily summary template: company and people, workflow steps, volumes and timing, tools, pain points, desired outcome and measure, decision makers, next steps |
| `meetily_reader.py` | Reads Meetily's local SQLite (a temporary copy, never the live file) and writes `transcript.md` plus `extraction.md`/`.json`. Every extracted item carries the closest transcript sentence and its timestamp, or is flagged `NO SUPPORTING QUOTE FOUND`. Standard library only. |
| `eval/` | The eval harness: synthetic call scripts (the ground truth), TTS render and mixing scripts, WER and checklist scoring, the hand audit, and the results |
| `tests/` | Unit tests for the reader and the scorer |

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
6. Before anything goes into an agent design, check every **next-step owner** and every item flagged `NO SUPPORTING QUOTE FOUND` by hand.

Leave every API-key field in Meetily empty. Everything above runs locally.

## Consent line (say it at the start of every call)

> "Before we start, I want to let you know this call is being recorded on my laptop so I can keep accurate notes. The recording stays with us and is not shared. Is that okay with you?"

Wait for a clear yes before you continue. Meetily joins no call as a bot, so nobody on the call can see it is recording. The spoken line is the notice, and it stays in the recording. Recording-consent law differs by state and country, and this line does not replace legal advice.

## Results (synthetic calls, Meetily Community 0.4.1, Mac mini M6 / 16 GB)

Three scripted discovery calls, 5.6 to 6.1 minutes each, voiced by two local TTS voices. Each call was run as a clean take, a noisy take (8 dB SNR) or a cross-talk take (12 overlapping turns). Summaries used Qwen 3.5 4B with the Axiom Discovery template. Full method, raw outputs and every caveat are in `eval/`.

| Call | Condition | Fed by | Word error | Checklist captured | Items linked to a quote | Wrong or vague next-step owners |
|---|---|---|---|---|---|---|
| HVAC intake | clean | import | 1.0% | 23/23 | 34/34 | 2 |
| HVAC intake | clean | live, via system audio | 1.2% | 22/23 (23/23 by hand) | 39/41 | 1 |
| Property maintenance | clean | import | 4.5% | 24/24 | 35/37 | 1 |
| Property maintenance | noise | import | 2.8% | 23/24 | 28/33 | 2 |
| Roofing follow-up | clean | import | 3.5% | 24/24 | 33/35 | 1 |
| Roofing follow-up | overlap | import | 13.6% | 22/24 | 27/30 | 1 |

What this shows and what it doesn't:
- Transcription is close to word for word on clear speech. **Cross-talk loses words.** In one case the summary then stated a wrong fact.
- Gemma 3 1B (the smallest built-in model) returned an empty outline with this template and got 8 of 23 checklist items with Meetily's own sales template.
- **There is no "who said what"**: the speaker field stayed empty on all 120 segments we recorded or imported. That is why next-step owners need a human check.
- Import dropped three whole sentences that fell right before a chunk boundary in one file. The drops repeated exactly on a re-import.
- No network connections were seen while recording, transcribing or summarizing. The app does contact GitHub at launch, which looks like its update check.
- The calls are synthetic TTS with no phone-line audio, accents or background voices, so real calls will score lower.

## Running the eval

```sh
python3 -m unittest discover -s tests
python3 eval/score.py --call call1-hvac --meeting <meeting-id> --method import-clean --summary-model qwen3.5-4b
python3 eval/report.py        # rebuilds eval/results/results.md
```
Rendering new audio needs a local Qwen3-TTS VoiceDesign environment (`eval/render.py`, then `eval/assemble.py <call> clean|noise|overlap`). Audio files are not in this repo.

## Credit

This kit is built on **Meetily** by Zackriya Solutions, MIT License: <https://github.com/Zackriya-Solutions/meetily> ([license](https://github.com/Zackriya-Solutions/meetily/blob/main/LICENSE.md)). It is not a fork and not affiliated with or endorsed by them. Meetily does the recording, transcription and summary. This repo adds the template, the reader and the eval. Speech recognition is NVIDIA Parakeet as bundled by Meetily. The test voices came from Qwen3-TTS VoiceDesign, run locally.

## License

MIT. See `LICENSE`.

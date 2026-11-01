# A183 · Meetily for Axiom: eval results

Run 2026-11-01 (Sunday) on the Mac mini (Apple M6, 16 GB RAM, macOS 27.0.1) with Meetily Community 0.4.1. The agent ran it and the numbers come from scripts. All audio is synthetic. There are no clients, no prospects and no real calls.

## Verdict (plain English)

- **PASS for Axiom's own discovery calls, with conditions.** Meetily heard our synthetic calls almost word for word: 1.0% to 4.5% word error on clean and noisy audio. With the Qwen 3.5 4B built-in model and our Axiom Discovery template, the summaries caught 22 to 24 of the 23 to 24 checklist items per call, 92% to 100% (workflow, volumes, tools, pains, next steps). Everything stayed on the Mac.
- **The smallest built-in model (Gemma 3 1B) FAILED.** With our template it returned an empty outline twice. With Meetily's own sales template it got 8 of 23 items and invented a date ("Wednesday, October 24, 2023"). Use Qwen 3.5 4B, a 2.6 GB download.
- **Cross-talk hurts.** When people talk over each other, word error rises to 13.6%. Overlapped words are lost, and in one case the summary filled the gap with a wrong fact ("two years" where the script says "three or four weeks").
- **There is no speaker split in practice.** Meetily's database has a `speaker` column (mic or system), but it stayed empty on all 120 segments across 8 meetings, both imported and live. The summaries also often put our next steps on the prospect, or the reverse. **A human must check every next-step owner before using a summary.**
- **Private in local mode, with one exception.** We saw zero network connections during recording, transcription or summarising (5 watch windows, polling once a second). At launch the app does contact GitHub, which looks like the update check. Analytics are off by default.
- **Custom templates work in the free Community edition.** We dropped one JSON file in a folder. The website says templates are Pro-only, but that was not true in 0.4.1.

Recommendation: use it on our own calls with Qwen 3.5 4B and the Axiom Discovery template. Say the consent line at the start. Ask one question at a time and don't talk over the prospect. Review the extraction's next-step owners and any item flagged "NO SUPPORTING QUOTE" before it goes into an agent design.

## Phase 1 · Pointing it at us

| Step | Observed |
|---|---|
| First launch | 13:49:23 CT. Microphone prompt appeared and was allowed from the agent seat (evidence/p1-01, p1-02). |
| Onboarding model pick | Onboarding offered **no choice**. It downloaded Parakeet and **Qwen 3.5 4B** automatically (p1-04). |
| Parakeet (parakeet-tdt-0.6b-v3-int8) | 670,619,706 bytes on disk (UI: 639.6 MB). Downloaded in about 9 s. |
| Qwen 3.5 4B Q4_K_M | 2,740,937,888 bytes (UI: 2614 MiB). Downloaded in about 46 s, in parallel with Parakeet. |
| Gemma 3 1B Q8_0 (smallest built-in) | 1,069,306,624 bytes (UI: ~1019 MiB). Downloaded in about 20 s from Settings > Summary, then selected (p1-17, p1-18, p1-20). |
| Launch to ready to record | About 3 minutes, including both downloads (13:49 to 13:52). |
| Settings stored | `settings` table shows `builtin-ai / gemma3:1b`, later `qwen3.5:4b`, and every API key column empty. No keys were entered. |
| System audio permission | Onboarding showed "Access Granted" but macOS did not list Meetily (p1-24). The real macOS prompt appeared on the **first recording**. The agent clicked Allow, and Meetily now shows ON under Privacy & Security > Screen & System Audio Recording > **System Audio Recording Only** (p1-27-system-audio-prompt, p1-31). Microphone shows ON (p1-23). Percy had nothing to do. |

### Open questions 1 to 6 from MEETILY.md section 7

1. **macOS floor.** Moot on this machine (27.0.1). The code needs 14.4 or later for Core Audio taps. Not tested on an older Mac.
2. **Custom templates in Community.** **Yes.** `~/Library/Application Support/Meetily/templates/axiom_discovery.json` appeared as "Axiom Discovery Call" in the per-meeting Template menu (p1-33, p1-34). The summary result records `template_id: axiom_discovery` and follows our 8 sections. The template is chosen per meeting, and every new meeting defaults to "Standard Meeting Notes", so it has to be picked each time.
3. **Audio kept, and size.** **Yes**, by default ("Save Audio Recordings" ON, p1-13), in `~/Movies/meetily-recordings/<meeting>/audio.mp4`: mono AAC, 48 kHz. Measured **61.5 MB per hour** for continuous speech (6,432,596 bytes for 376.8 s) and 8.8 MB per hour for a mostly quiet test. Imported files are **copied** in whole: a 6-minute 24 kHz WAV adds 17 MB.
4. **Accuracy.** See Phase 2. This is synthetic TTS audio, not phone-line audio, so real calls will score worse.
5. **Reading the SQLite and JSON.** **Yes.** The database is `~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite`, with tables `meetings`, `transcripts` (text, audio_start_time, audio_end_time, speaker), `summary_processes` (`result` JSON with `markdown`), `settings` and `transcript_chunks`. Each meeting folder holds `metadata.json` and `transcripts.json`. `meetily_reader.py` reads a temporary copy, so it never locks the app. Two quirks: (a) after a summary, Meetily **renames the meeting** to a title it generates. Once that was the literal "<Add Title here>". Track meetings by id, not title. (b) `speaker` is always NULL (see Phase 2).
6. **Network in local mode.** Every second we polled `lsof` for Meetily and its child processes (llama-helper, ffmpeg) and took `nettop` snapshots. We saw **0 internet sockets** during the 1-minute test recording, the 6-minute live session, all 9 summary runs (one only partly inside a watch window) and idle time (evidence/net-*.txt). A 0.2 s poll at app launch caught **2 connections**: `140.82.114.3:443` (GitHub) and `185.199.109.133:443` (GitHub's raw-content CDN), which matches the updater. We found no setting to turn it off. `analytics.json` shows `analyticsOptedIn: false`. A 1 s poll can miss a very short connection. It did: the 1 s watcher was still running at the 14:49:53 relaunch and logged nothing, while the 0.2 s poll caught the GitHub connections. So this proves no long-lived traffic during calls, not zero packets.

## Phase 2 · Eval

### Test set
Three scripted Axiom discovery calls, all fictional companies and people. Each is about 1,000 to 1,160 words and 5.6 to 6.1 minutes long. Every call opens with the consent line. The scripts are the ground truth: `eval/scripts/`.

| File | Business | Condition | Length |
|---|---|---|---|
| call1-hvac-clean | HVAC after-hours intake | clean | 6:00 |
| call2-property-noise | Property-management maintenance requests | pink noise plus 60 Hz hum at 8 dB SNR | 6:07 |
| call3-roofing-overlap | Roofing estimate follow-up | 12 turns start 0.9 to 1.6 s before the other speaker finishes | 5:39 |
| call2-property-clean, call3-roofing-clean | same scripts | clean controls | 6:07, 6:00 |

Voices: local Qwen3-TTS 1.7B VoiceDesign (run locally). One designed voice plays the Axiom interviewer and a different designed voice plays each prospect. Each line was rendered separately and placed on a timeline (`render.py`, `assemble.py`).

### How the audio was fed in
- **Import** (Settings > Beta > Import Audio & Retranscribe, Parakeet): all five files. A 6-minute file took under 20 s.
- **Live recording**: call 1 was played through the Mac's system audio with `afplay` while Meetily recorded (mic = DJI Mic Mini, system = global Core Audio tap). This is the path a real Zoom or Meet call takes.
- Summaries: Generate Summary with the Axiom Discovery template, run on each meeting.

### Scores
Scored by `eval/score.py`. WER uses `textnorm.normalise` on both sides: numbers become words, and spacing-only product-name variants like "Job Nimbus" and "JobNimbus" count as the same word. The checklist is matched automatically against the summary (`checklists.json`, built from the scripts before any output was seen). The last two columns come from a hand audit (`results/hand-audit.json`).

| Call | Condition | How it was fed | WER | Sub / Del / Ins | Source labels | Checklist (auto) | Items linked to a quote | Factual errors (hand) | Wrong or vague owners (hand) |
|---|---|---|---|---|---|---|---|---|---|
| call1-hvac | clean | import | 1.0% | 4 / 5 / 3 of 1157 | unlabelled 15 | 23/23 | 34/34 | 1 | 2 |
| call1-hvac | live (system audio) | played through system audio while recording | 1.2% | 7 / 3 / 4 of 1157 | unlabelled 30 | 22/23 | 39/41 | 2 | 1 |
| call2-property | clean | import | 4.5% | 6 / 39 / 3 of 1076 | unlabelled 15 | 24/24 | 35/37 | 1 | 1 |
| call2-property | noise | import | 2.8% | 16 / 10 / 4 of 1076 | unlabelled 14 | 23/24 | 28/33 | 0 | 2 |
| call3-roofing | clean | import | 3.5% | 4 / 31 / 0 of 1006 | unlabelled 15 | 24/24 | 33/35 | 2 | 1 |
| call3-roofing | overlap | import | 13.6% | 18 / 117 / 2 of 1006 | unlabelled 14 | 22/24 | 27/30 | 2 | 1 |

Summaries above: Qwen 3.5 4B (built-in, local) with the Axiom Discovery template. Summary time was 30 to 42 s per 6-minute call.

| Smallest built-in model, Gemma 3 1B, call 1 | Checklist (auto) |
|---|---|
| Axiom Discovery template | 0/23 (empty section headings, 2 of 2 runs) |
| bundled Client / Sales template | 8/23, plus an invented date |

The one live-session checklist miss (w4, "calls each person back") is a scorer false negative. The summary says "Dispatcher calls customer to book job". By hand, the live session scored 23/23.

### What failed or is weak
1. **Speaker split: FAIL / not available.** The `speaker` column was NULL on 120 of 120 segments, and `transcripts.json` has no source field. The live recording is saved as one mixed mono file, so we couldn't score mic vs system. This explains the owner errors: the model can't tell who said what. Every next-step table had at least one wrong or vague owner, for example "Interviewer sends the 10 emails" when the prospect sends them.
2. **Import drops speech at chunk ends.** Import cuts audio into chunks of about 22 to 27 s. In call 2 (clean), three whole utterances right before a chunk boundary disappeared, 39 deletions in total, for example "Our leasing team says they get about thirty status calls a week...". Re-importing gave **the same three drops** (deterministic). The noisy copy of the same script did not drop them. Live recording (shorter segments) had only 3 deletions on call 1.
3. **Cross-talk: 117 deletions.** Overlapped speech is mostly lost. In the overlap file the summary missed CompanyCam, "three or four inspections a day" and the $800 repair figure, and it wrote "two years" where the script says "three or four weeks".
4. **Gemma 3 1B is unusable for this** (see above).
5. **Template is not sticky.** Each new meeting defaults to Standard Meeting Notes.
6. **The summary renames the meeting**, once to "<Add Title here>".

### Discovery template and reader
- Template: `templates/axiom_discovery.json` (8 sections: company and people, workflow steps, volumes and timing, tools, pain points, desired outcome and measure, decision makers, next steps).
- Reader: `meetily_reader.py` (stdlib only). It writes `transcript.md` (time-stamped) and `extraction.md`/`.json`: process map, volumes, tools, pain list, outcome, decision makers, next steps and candidate agent tasks. **Each item is linked to the closest 1 to 3 transcript sentences with a timestamp.** Items with no supporting sentence are flagged `NO SUPPORTING QUOTE FOUND`. On the 6 Qwen summaries, 196 of 210 items (93%) linked to a quote. The quote link catches statements the model invented that are not in the transcript (unit test). It cannot catch an error that is already in the transcript, such as the "two years" mistranscription, because the quote then "supports" it. Outputs: `eval/results/extractions/`.
- Tests: `python3 -m unittest discover -s tests` passes all 6 tests.

## Evidence
Screenshots of setup, settings, permissions, the template menu, the import dialog and the summaries, plus the network-watch logs, are kept in Axiom's internal work folder because they show our desktop. The raw Meetily outputs behind every number are in this repo: `eval/results/meetily-out/` (summary JSON), `eval/results/transcripts-raw/`, `eval/results/extractions/`, `eval/results/scores/`, `eval/results/timelines/`.

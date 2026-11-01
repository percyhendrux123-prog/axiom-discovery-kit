# Network-watch logs (sanitized)

Raw output of `eval/netwatch.sh` and one fast poll, from the eval Mac on 2026-11-01 (times are US Central). The only edits are that the local user name became `<user>` and the LAN address became `<lan-ip>`.

How it was watched: `lsof -nP -i` on the Meetily process, its child processes and `llama-helper`, in a loop meant to run once a second. Each pass takes a little longer than a second (30 passes took about 39 s), so the real interval is about 1.3 s. Every 30 passes a `nettop` snapshot was filtered for `meetily|llama|ffmpeg`. An empty `nettop` line means no such row appeared.

| File | Window (CT) | What Meetily was doing | Internet sockets seen |
|---|---|---|---|
| `net-idle-after-setup.txt` | one lsof snapshot at 13:58:08 | idle after setup | 0 |
| `net-test-recording.txt` | 14:01:03 to 14:02:21 | 1-minute live test recording and its transcription | 0 |
| `net-summary-call1-gemma1b.txt` | 14:24:33 to 14:29:39 | Gemma 3 1B summaries of call 1 | 0 |
| `net-summaries-qwen4b.txt` | 14:38:50 to 14:58:14 | Qwen 3.5 4B summaries, the live session, the 14:49:53 relaunch, and the re-import of call 2 clean (14:52:57) | 0 |
| `net-live-session-call1.txt` | 14:42:56 to 14:52:01 | live recording of call 1 through system audio, with live transcription | 0 |
| `net-summary-live-qwen4b.txt` | 14:51:10 to 14:53:47 | summary of the live session | 0 |
| `net-relaunch-fastpoll.txt` | 40 s from 14:49:53, lsof every 0.2 s | app relaunch | 2 connections (3 lines): 140.82.114.3:443 (GitHub) and 185.199.109.133:443 (GitHub raw-content CDN) |

Limits:
- The ~1.3 s loop misses short connections. It was running during the 14:49:53 relaunch and logged nothing, while the 0.2 s poll caught the two GitHub connections. So these logs show no connection was open long enough to be seen. They do not prove that zero packets were sent.
- The imports of the five scored files (14:24 for call 1, then 14:33 to 14:36) were not inside a watch window. Transcription was watched during the live session, the 1-minute test and the re-import of call 2 clean.
- No packet capture was run.

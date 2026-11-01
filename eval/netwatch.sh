#!/bin/bash
# netwatch.sh <outfile> <seconds>
# Polls every second for internet sockets owned by Meetily and its child processes
# (llama-helper, ffmpeg) and logs them; also takes nettop per-process byte snapshots.
OUT="$1"; SECS="${2:-600}"
: > "$OUT"
echo "netwatch start $(date '+%F %T')  secs=$SECS" >> "$OUT"
for ((i=0; i<SECS; i++)); do
  P=$(pgrep -f "meetily.app/Contents/MacOS/meetily" | head -1)
  PIDS="$P $(pgrep -P "$P" 2>/dev/null | tr '\n' ' ') $(pgrep -f llama-helper | tr '\n' ' ')"
  for p in $PIDS; do
    lsof -nP -i -a -p "$p" 2>/dev/null | tail -n +2 | sed "s/^/$(date +%T) /" >> "$OUT"
  done
  if (( i % 30 == 0 )); then
    echo "nettop $(date +%T):" >> "$OUT"
    nettop -P -L 1 -x -J bytes_in,bytes_out 2>/dev/null | grep -i -E "meetily|llama|ffmpeg" >> "$OUT"
  fi
  sleep 1
done
echo "netwatch end $(date '+%F %T')" >> "$OUT"
echo "socket lines: $(grep -c -E 'TCP|UDP' "$OUT")" >> "$OUT"

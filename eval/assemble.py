"""Assemble rendered lines into a call: mix + per-speaker stems + timeline.

Usage: python assemble.py call1-hvac clean|noise|overlap
Needs numpy + soundfile (use the qwen venv).
Outputs eval/audio/<call>/{mix.wav, stem-A.wav, stem-P.wav, timeline.json}
"""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf

HERE = Path(__file__).parent
GAP = 0.45            # seconds of silence between turns
OVERLAP = (0.9, 1.6)  # seconds the next speaker starts early in the overlap condition
SNR_DB = 8.0          # noise condition: speech-to-noise ratio


def pink(n, rng):
    # Voss-McCartney-ish pink noise via 1/f filtering in the frequency domain
    white = rng.standard_normal(n)
    f = np.fft.rfft(white)
    k = np.arange(len(f)); k[0] = 1
    return np.fft.irfft(f / np.sqrt(k), n)


def main(call, cond):
    d = HERE / "audio" / call
    lines = json.loads((d / "lines.json").read_text())
    rng = np.random.default_rng(7)
    wavs, sr = [], None
    for i in range(len(lines)):
        w, s = sf.read(str(d / f"line-{i:03d}.wav"), dtype="float32")
        if w.ndim > 1:
            w = w.mean(axis=1)
        sr = sr or s
        assert s == sr
        wavs.append(w / (np.abs(w).max() + 1e-9) * 0.7)
    # place lines on a timeline
    t, starts = 0.5, []
    prev_spk = None
    for i, w in enumerate(wavs):
        if i and cond == "overlap" and lines[i]["spk"] != prev_spk and i % 3 == 0 and len(wavs[i - 1]) / sr > 2.5:
            start = max(starts[-1] + 0.5, t - rng.uniform(*OVERLAP))
        else:
            start = t + (GAP if i else 0)
        starts.append(start)
        t = start + len(w) / sr
        prev_spk = lines[i]["spk"]
    n = int((t + 0.8) * sr)
    stem = {"A": np.zeros(n, np.float32), "P": np.zeros(n, np.float32)}
    timeline = []
    for i, (w, st) in enumerate(zip(wavs, starts)):
        a = int(st * sr)
        stem[lines[i]["spk"]][a:a + len(w)] += w
        timeline.append({"i": i, "spk": lines[i]["spk"], "start": round(st, 3),
                         "end": round(st + len(w) / sr, 3), "text": lines[i]["text"]})
    mix = stem["A"] + stem["P"]
    if cond == "noise":
        speech_rms = np.sqrt(np.mean(mix[np.abs(mix) > 0.01] ** 2))
        nz = pink(n, rng)
        hum = 0.3 * np.sin(2 * np.pi * 60 * np.arange(n) / sr)  # mains hum
        nz = nz / np.sqrt(np.mean(nz ** 2)) + hum
        nz = nz / np.sqrt(np.mean(nz ** 2)) * speech_rms / (10 ** (SNR_DB / 20))
        mix = mix + nz.astype(np.float32)
    peak = np.abs(mix).max()
    if peak > 0.98:
        mix = mix / peak * 0.98
    sf.write(str(d / "mix.wav"), mix, sr)
    sf.write(str(d / "stem-A.wav"), stem["A"], sr)
    sf.write(str(d / "stem-P.wav"), stem["P"], sr)
    ov = sum(1 for i in range(1, len(timeline)) if timeline[i]["start"] < timeline[i - 1]["end"])
    meta = {"call": call, "condition": cond, "sample_rate": sr, "duration_s": round(n / sr, 1),
            "lines": len(lines), "overlapping_turns": ov,
            "snr_db": SNR_DB if cond == "noise" else None, "timeline": timeline}
    (d / "timeline.json").write_text(json.dumps(meta, indent=1))
    print(call, cond, "duration", meta["duration_s"], "s; overlaps", ov)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

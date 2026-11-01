"""Render synthetic two-voice discovery calls with Qwen3-TTS VoiceDesign (local).

Usage: ~/dev/voice-lab/qwen/.venv/bin/python render.py call1-hvac [call2-property ...]
Writes eval/audio/<call>/line-NNN.wav (one per script line) and lines.json.
Assembly (gaps, noise, overlap, stems) is done by assemble.py.
"""
import faulthandler, json, os, sys, time
from pathlib import Path
import torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

HERE = Path(__file__).parent
VOICES = {
    "A": "A calm, clear male voice in his late 30s with a neutral American accent. "
         "Mid-range pitch, friendly and professional, steady conversational pace, "
         "like a consultant asking careful questions on a phone call. Not an announcer.",
    "call1-hvac": "A warm female voice in her mid 40s with a light Southern accent. "
                  "Practical and direct, a busy office manager explaining her day on a call. "
                  "Natural conversational pace, slightly faster than average.",
    "call2-property": "A female voice in her early 30s with a neutral Midwestern American accent. "
                      "Organized and a little tired, speaking plainly and quickly on a work call.",
    "call3-roofing": "A deep male voice in his early 50s with a Texas accent, a little gravel. "
                     "Straight-talking small business owner, relaxed and confident, conversational.",
}
BATCH = 1
ATTEMPT = int(os.environ.get('RENDER_ATTEMPT', '0'))


def parse(path):
    lines = []
    for raw in path.read_text().splitlines():
        if raw.startswith("A: ") or raw.startswith("P: "):
            lines.append({"spk": raw[0], "text": raw[3:].strip()})
    return lines


def main():
    calls = sys.argv[1:]
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", device_map="mps", dtype=torch.float16)
    for call in calls:
        lines = parse(HERE / "scripts" / f"{call}.txt")
        out = HERE / "audio" / call
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        for spk in ("A", "P"):
            instruct = VOICES["A"] if spk == "A" else VOICES[call]
            idx = [i for i, l in enumerate(lines) if l["spk"] == spk]
            for b in range(0, len(idx), BATCH):
                chunk = [i for i in idx[b:b + BATCH] if not (out / f"line-{i:03d}.wav").exists()]
                if not chunk:
                    continue
                torch.manual_seed((1101 if spk == "A" else 2202) + 17 * ATTEMPT + chunk[0])
                faulthandler.dump_traceback_later(150, exit=True)  # MPS hang watchdog
                wavs, sr = model.generate_voice_design(
                    text=[lines[i]["text"] for i in chunk],
                    instruct=[instruct] * len(chunk),
                    language=["English"] * len(chunk))
                faulthandler.cancel_dump_traceback_later()
                for i, w in zip(chunk, wavs):
                    sf.write(str(out / f"line-{i:03d}.wav"), w, sr)
                print(call, spk, chunk, round(time.time() - t0, 1), "s", flush=True)
        (out / "lines.json").write_text(json.dumps(lines, indent=1))
        print("DONE", call, round(time.time() - t0, 1), "s", flush=True)


if __name__ == "__main__":
    main()

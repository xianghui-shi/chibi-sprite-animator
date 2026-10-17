#!/usr/bin/env python3
"""口播音频 → SRT（Whisper）。转写后必须人工校对（专有名词、同音字最容易错）。

用法: python transcribe_srt.py 音频.wav 输出.srt [--model small] [--prompt "提示词：人名、话题"]
依赖: pip install faster-whisper numpy ；系统需有 ffmpeg
说明: 先用 ffmpeg 转成 16k 单声道 float32 再喂给模型，绕开部分 PyAV 版本的兼容问题。
"""
import argparse, subprocess, sys, tempfile, os
import numpy as np

def ts(sec: float) -> str:
    ms = int(round(sec * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio"); ap.add_argument("out")
    ap.add_argument("--model", default="small"); ap.add_argument("--lang", default="zh")
    ap.add_argument("--prompt", default="以下是普通话口播。")
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    raw = os.path.join(tempfile.mkdtemp(), "a.raw")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.audio, "-ar", "16000", "-ac", "1", "-f", "f32le", raw], check=True)
    audio = np.fromfile(raw, dtype=np.float32)
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language=a.lang, initial_prompt=a.prompt)
    lines = []
    for i, s in enumerate(segs, 1):
        lines.append(f"{i}\n{ts(s.start)} --> {ts(s.end)}\n{s.text.strip()}\n")
    open(a.out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"已写入 {a.out}（{len(lines)} 条）——请逐句人工校对后再继续")

if __name__ == "__main__":
    sys.exit(main())

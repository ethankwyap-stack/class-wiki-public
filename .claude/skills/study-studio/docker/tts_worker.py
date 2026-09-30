"""Runs inside the container. stdin: JSON [[voice, text], ...] -> /out/out.wav"""
import json, sys
import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

kokoro = Kokoro("/models/kokoro-v1.0.fp16.onnx", "/models/voices-v1.0.bin")
parts, rate = [], 24000
for voice, text in json.load(sys.stdin):
    audio, rate = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
    parts += [audio, np.zeros(int(rate * 0.35), dtype=audio.dtype)]  # short pause between turns
sf.write("/out/out.wav", np.concatenate(parts), rate)

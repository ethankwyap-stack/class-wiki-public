# Kokoro TTS sandbox. Built once by make_audio.py; always run with --network none.
FROM python:3.12-slim
RUN pip install --no-cache-dir kokoro-onnx==0.6.1 soundfile==0.13.1
COPY tts_worker.py /tts_worker.py
ENTRYPOINT ["python", "/tts_worker.py"]

# 하네스 기본 전사기(faster-whisper) — media.js 가 python 에 faster_whisper 가 있으면 쓴다.
#   python transcribe_fw.py "<입력>" "<출력 폴더>" → <출력 폴더>/<이름>.txt (구간 시각 포함). 모델 · 언어는 환경 변수로:
#   HARNESS_FW_MODEL(기본 small) · HARNESS_FW_LANG(기본 자동 감지). 처음 쓸 때 모델을 한 번 내려받는다(폐쇄망이면 미리 받아 둔다).
import os
import sys

from faster_whisper import WhisperModel

src, outdir = sys.argv[1], sys.argv[2]
model = WhisperModel(os.environ.get("HARNESS_FW_MODEL", "small"), device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
segments, info = model.transcribe(src, language=os.environ.get("HARNESS_FW_LANG") or None, vad_filter=True, beam_size=5)
os.makedirs(outdir, exist_ok=True)
out = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(f"# language={info.language} p={info.language_probability:.2f} duration={info.duration:.1f}s\n")
    for s in segments:
        f.write(f"[{int(s.start // 60):02d}:{int(s.start % 60):02d}] {s.text.strip()}\n")
print(out)

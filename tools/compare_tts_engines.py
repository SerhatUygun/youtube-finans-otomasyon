"""TTS motor karşılaştırması: aynı Türkçe script'i s02_tts ile farklı motorlarda seslendirir,
süreyi ölçer, faster-whisper ile geri yazıya döküp metne benzerliğini (anlaşılırlık) raporlar.

Kullanım: .venv/Scripts/python.exe tools/compare_tts_engines.py [motor ...]
Varsayılan: xtts_v2 voxcpm. Çıktılar output/_tts_compare_<motor>/ altına yazılır.
"""
import difflib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import tr_number_speech
from pipeline.stages import s02_tts
from pipeline.utils.config import load_config
from pipeline.utils.paths import job_path

SEGMENTS = [
    "Merhaba, Finans Kanalı'ya hoş geldiniz. Bugün doların neden yükseldiğini birlikte inceleyeceğiz.",
    "Borsa İstanbul yüzde 1,9 değer kazanırken gram altın 4.250 liraya çıktı.",
    "Merkez Bankası'nın faiz kararı, önümüzdeki haftalarda piyasaların yönünü belirleyecek.",
    "Unutmayın, burada paylaştıklarım yatırım tavsiyesi değildir; kararlarınızı kendi araştırmanızla verin.",
]


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^\w ]", " ", t.replace("I", "ı").replace("İ", "i").lower()).split())


def main():
    engines = sys.argv[1:] or ["xtts_v2", "voxcpm"]
    base_cfg = load_config()

    from faster_whisper import WhisperModel
    # faster-whisper (ctranslate2) Blackwell'de cuBLAS hatası veriyor -> CPU.
    wm = WhisperModel("small", device="cpu", compute_type="int8")

    expected = " ".join(tr_number_speech.normalize_for_tts(s) for s in SEGMENTS)
    results = {}
    for engine in engines:
        job = f"_tts_compare_{engine}"
        job_path(job, "x").parent.mkdir(parents=True, exist_ok=True)
        job_path(job, "script.json").write_text(
            json.dumps({"segments": SEGMENTS, "script": " ".join(SEGMENTS), "language": "tr"}, ensure_ascii=False),
            encoding="utf-8",
        )
        cfg = json.loads(json.dumps(base_cfg))
        cfg["tts"]["engine"] = engine
        s02_tts.load_config = lambda cfg=cfg: cfg

        t0 = time.time()
        try:
            out = s02_tts.run(job)
        except Exception as e:  # noqa: BLE001 — karşılaştırma raporu için hatayı kaydet
            results[engine] = {"error": str(e)[-1500:]}
            print(f"[{engine}] HATA: {e}")
            continue
        elapsed = time.time() - t0

        segs, info = wm.transcribe(out["audio_file"], language="tr")
        heard = " ".join(s.text for s in segs).strip()
        sim = difflib.SequenceMatcher(None, _norm(expected), _norm(heard)).ratio()
        results[engine] = {
            "audio": out["audio_file"],
            "audio_sec": round(out["duration_ms"] / 1000, 1),
            "synth_sec": round(elapsed, 1),
            "similarity": round(sim, 3),
            "transcript": heard,
        }
        print(f"[{engine}] {results[engine]}")

    report = job_path("_tts_compare_report", "report.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"expected": expected, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rapor: {report}")


if __name__ == "__main__":
    main()

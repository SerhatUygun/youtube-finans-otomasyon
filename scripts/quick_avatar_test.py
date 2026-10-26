"""Hizli EchoMimic V2 avatar testi: beyin (yerel Ollama) ile kisa TR script uretir,
TTS (xtts_v2) ile seslendirir, sonra s03_avatar (echomimic) ile konusan video uretir.
Gorsel/broll/altyazi/final montaj atlanir - sadece avatar kalitesini kontrol icin.

Kullanim: .venv/Scripts/python.exe scripts/quick_avatar_test.py --topic "..." --words 150
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from pipeline.utils.paths import job_path  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--words", type=int, default=150)
    ap.add_argument("--language", default="tr")
    ap.add_argument("--job-id", default="_echomimic_quicktest")
    args = ap.parse_args()

    from pipeline import persona
    from pipeline.utils.config import load_config

    print(f"[1/3] Beyin script uretiyor ({args.words} kelime, {args.language}) ...")
    gen = persona.generate_researched_script(args.topic, target_words=args.words, language=args.language)
    segments = gen.get("segments") or []
    if not segments:
        raise SystemExit("script uretilemedi (segment yok)")

    script_payload = {
        "topic": gen.get("topic", args.topic),
        "script": gen.get("script", ""),
        "segments": segments,
        "visual_prompts": gen.get("visual_prompts", []),
        "language": gen.get("language", args.language),
    }
    job_path(args.job_id, "script.json").write_text(
        json.dumps(script_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    -> {len(segments)} segment, {len(script_payload['script'].split())} kelime")

    # Ollama VRAM'i bosalt (TTS + EchoMimic ayni GPU'yu kullanacak)
    persona.unload_model()

    print("[2/3] TTS (xtts_v2) ...")
    from pipeline.stages import s02_tts
    s02_tts.run(args.job_id)
    print(f"    -> {job_path(args.job_id, 'audio.wav')}")

    print("[3/3] EchoMimic V2 avatar render ...")
    from pipeline.stages import s03_avatar
    res = s03_avatar.run(args.job_id)
    print("TAMAM ->", res)


if __name__ == "__main__":
    main()

"""17 Eyl eklendi: pipeline/tr_number_speech.py için regresyon testi.

Amaç: para birimi/sıra sayısı/kısaltma normalizasyonu ileride bir değişiklikle
sessizce bozulursa hemen fark edilsin (Ollama/GPU gerekmez, saniyeler içinde çalışır).

Kullanım:
    python tools/test_tr_number_speech.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tr_number_speech import normalize_for_tts  # noqa: E402

CASES = [
    ("Dolar bugün 47,69 Türk lirası seviyesinden işlem gördü.",
     "Dolar bugün kırk yedi virgül altmış dokuz Türk lirası seviyesinden işlem gördü."),
    ("Bu rakam son bir ay içinde yaklaşık %1,9 oranında artışa işaret ediyor.",
     "Bu rakam son bir ay içinde yaklaşık yüzde bir virgül dokuz oranında artışa işaret ediyor."),
    ("Gram altının o dönemde 6.170 lira bandında dengelendiği belirtilmişti.",
     "Gram altının o dönemde altı bin yüz yetmiş lira bandında dengelendiği belirtilmişti."),
    ("Dolar bugün $47,69 seviyesinden işlem gördü.",
     "Dolar bugün kırk yedi virgül altmış dokuz dolar seviyesinden işlem gördü."),
    ("Gram altın ₺6.170 bandında dengelendi.",
     "Gram altın altı bin yüz yetmiş lira bandında dengelendi."),
    ("S&P 500 endeksi bugün 7.745 dolar seviyesinden işlem gördü.",
     "es end pi beş yüz endeksi bugün yedi bin yedi yüz kırk beş dolar seviyesinden işlem gördü."),
    ("Bu ayın 20. günü açıklanan veriler beklentileri aştı.",
     "Bu ayın yirminci günü açıklanan veriler beklentileri aştı."),
    ("21. yüzyılın en büyük faiz artışı olarak kayıtlara geçti.",
     "yirmi birinci yüzyılın en büyük faiz artışı olarak kayıtlara geçti."),
    ("Kar ve zarar (P&L) tablosunda 3. çeyrek verileri paylaşıldı.",
     "Kar ve zarar (P ve L) tablosunda üçüncü çeyrek verileri paylaşıldı."),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    failures = 0
    for src, expected in CASES:
        got = normalize_for_tts(src)
        if got != expected:
            failures += 1
            print(f"BAŞARISIZ:\n  girdi   : {src}\n  beklenen: {expected}\n  alınan  : {got}\n")
    if failures:
        print(f"{failures}/{len(CASES)} test başarısız.")
        return 1
    print(f"Tüm {len(CASES)} test geçti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""27 Temmuz 2026 için TEMELLENDİRİLMİŞ (gerçek web-araştırma verili) Türkçe örnek işleri
oluşturur. Scriptler elle, doğrulanmış verilerle yazıldı (LLM'nin yavaş/kararsız olması
nedeniyle güvenilirlik için); sayılar TTS'in doğru okuması için kelimeyle yazıldı.
Her iş için script.json + metadata.json yazar, job_id'leri overnight_jobs.json'a döker.
"""
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.utils.paths import OUTPUT_DIR  # noqa: E402


def _slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()[:40] or "job"


EXAMPLES = [
    {
        "title": "Altın ve Gümüşte Son Durum | 27 Temmuz 2026",
        "topic": "27 Temmuz 2026 altın ve gümüş piyasası",
        "tags": ["altın", "gümüş", "altın fiyatı", "gümüş fiyatı", "ekonomi", "piyasa",
                 "yatırım", "finans", "borsa", "gold", "silver", "Shorts"],
        "description": "27 Temmuz 2026'da altın ve gümüşte ne oldu? Fiyatlar, nedenleri ve piyasanın gözü. #Shorts #altın #gümüş #ekonomi",
        "pairs": [
            ("27 Temmuz 2026'da altın ve gümüşte hareketli bir gün yaşandı.",
             "Stacks of shiny gold bars in a bank vault, warm cinematic lighting"),
            ("Altın, ons başına yaklaşık dört bin seksen dolardan işlem gördü.",
             "A large glowing gold bar with a rising green financial chart behind it"),
            ("Gün içinde yüzde sıfır virgül yedi değer kazandı.",
             "An upward green candlestick stock chart with a gold coin in front"),
            ("Gümüş ise daha güçlüydü; yüzde iki virgül yirmi altı yükseldi.",
             "Bright silver coins and bars glinting under studio spotlight"),
            ("Gümüşün onsu elli dokuz virgül kırk üç dolara çıktı.",
             "A close-up of stacked silver bars with a rising silver price ticker"),
            ("Altın-gümüş oranı altmış sekize geriledi, yani gümüş daha hızlı kazandı.",
             "A balance scale weighing one gold bar against many silver coins"),
            ("Yükselişin arkasında ABD ile İran arasındaki çatışmaya verilen ara vardı.",
             "A calm white dove flying over a world map with the Middle East highlighted"),
            ("Güvenli liman talebi altını ve gümüşü yukarı taşıdı.",
             "Golden safe-haven shield protecting coins during a storm, cinematic"),
            ("Piyasalar, Fed'in faizi sabit tutmasını bekliyordu.",
             "The US Federal Reserve building with a glowing percentage symbol"),
            ("Gümüşü ayrıca güçlü sanayi talebi ve arz açığı destekledi.",
             "A factory with solar panels and electronics that use silver, industrial"),
            ("Yine de her iki metal de ocak ayındaki rekor seviyelerin altındaydı.",
             "A line chart falling from a high peak, gold and silver bars below"),
            ("Sıradaki kritik veri, otuz Temmuz'daki enflasyon rakamlarıydı.",
             "A calendar page marked July 30 surrounded by financial charts"),
        ],
    },
    {
        "title": "Dünya ve Ekonomi Gündemi | 27 Temmuz 2026",
        "topic": "27 Temmuz 2026 dünya ve ekonomi gündemi",
        "tags": ["gündem", "dünya haberleri", "ekonomi", "petrol", "borsa", "enflasyon",
                 "faiz", "haberler", "finans", "piyasa", "news", "Shorts"],
        "description": "27 Temmuz 2026'da dünya ve ekonomide öne çıkanlar: ateşkes, petrol, faiz ve borsalar. #Shorts #ekonomi #gündem #haberler",
        "pairs": [
            ("İşte 27 Temmuz 2026'da dünya ve ekonomi gündemi.",
             "A spinning glowing globe with abstract news ticker headlines around it"),
            ("En büyük gelişme, ABD ile İran'ın hava saldırılarına ara vermesiydi.",
             "A world map with a peace symbol glowing over the Middle East"),
            ("Diplomasi, Hürmüz Boğazı'nı yeniden açmaya odaklandı.",
             "A large oil tanker sailing through a narrow sea strait at golden sunset"),
            ("Gerilim azalınca petrol fiyatları yaklaşık yüzde sekiz düştü.",
             "A sharply falling red oil price chart with oil barrels in the foreground"),
            ("Altın dört bin seksen dolara yükselirken gümüş sıçradı.",
             "Gold bars and silver coins side by side, both glowing warmly"),
            ("ABD Merkez Bankası'nın faizi sabit tutması bekleniyordu.",
             "The Federal Reserve building with interest rate arrows and a dollar sign"),
            ("Enflasyon hâlâ yüksekti; yıllık yüzde üç buçuk seviyesindeydi.",
             "A shopping cart full of groceries with a rising red price graph"),
            ("Borsalarda tablo karışıktı; teknoloji hisseleri geriledi.",
             "Stock market screens showing mixed red and green numbers, abstract"),
            ("Yatırımcılar dev teknoloji şirketlerinin bilançolarını bekliyordu.",
             "Four glowing abstract tech towers in a futuristic city skyline at night"),
            ("Avrupa'da orman yangınları üç yüz altmış binden fazla kişiyi tahliyeye zorladı.",
             "A wildfire on a hillside with firefighters and evacuation, dramatic smoky sky"),
            ("Kısacası, jeopolitik gerilim tüm piyasaları hareketlendirdi.",
             "A world map with connected glowing lines linking oil, gold and stock icons"),
        ],
    },
    {
        "title": "Günün Piyasa Özeti | 27 Temmuz 2026",
        "topic": "27 Temmuz 2026 hızlı piyasa özeti",
        "tags": ["piyasa özeti", "altın", "gümüş", "petrol", "ekonomi", "faiz",
                 "finans", "borsa", "yatırım", "Shorts"],
        "description": "Altın, gümüş ve petrolde günün özeti — 30 saniyede. 27 Temmuz 2026. #Shorts #ekonomi #altın #petrol",
        "pairs": [
            ("27 Temmuz 2026 piyasa özeti, otuz saniyede.",
             "A fast news intro with a ticking clock and financial tickers, dynamic"),
            ("Altın dört bin seksen dolar, yüzde sıfır virgül yedi artıda.",
             "A gold bar with a bright upward green arrow and rising chart"),
            ("Gümüş parladı; yüzde iki virgül yirmi altı yukarıda.",
             "Silver coins stacking up with a glowing upward arrow"),
            ("Petrol ise çakıldı, yaklaşık yüzde sekiz düştü.",
             "A crashing red oil price chart with tumbling oil barrels"),
            ("Sebep, ABD ve İran arasındaki ateşkes ve güvenli liman talebiydi.",
             "A calm dove over a world map with the Middle East highlighted"),
            ("Tüm gözler, Fed'in faiz kararındaydı.",
             "The Federal Reserve building under a dramatic spotlight, dollar sign"),
            ("Takipte kal; yarın yine buradayız.",
             "A glowing upward market chart with an abstract subscribe icon, energetic"),
        ],
    },
]


def main():
    job_ids = []
    for i, ex in enumerate(EXAMPLES, 1):
        segments = [p[0] for p in ex["pairs"]]
        visual_prompts = [p[1] for p in ex["pairs"]]
        job_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{_slug(ex['topic'])}-ex{i}"
        d = OUTPUT_DIR / job_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "script.json").write_text(json.dumps({
            "topic": ex["topic"],
            "script": " ".join(segments),
            "segments": segments,
            "visual_prompts": visual_prompts,
            "language": "tr",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / "metadata.json").write_text(json.dumps({
            "title": ex["title"],
            "description": ex["description"],
            "tags": ex["tags"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        job_ids.append(job_id)
        print(f"[{i}] {job_id}  ({len(segments)} segment)")

    (ROOT / "scripts" / "overnight_jobs.json").write_text(
        json.dumps(job_ids, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(job_ids)} iş hazır -> overnight_jobs.json")


if __name__ == "__main__":
    main()

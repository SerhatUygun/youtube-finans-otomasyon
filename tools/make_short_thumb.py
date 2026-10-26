"""6 Eki: Shorts kapağı (1080x1920 dikey) — reel'in kendi karesinden + üstte büyük başlık.

Reel'in ~2. saniyesi genelde Stamp sahnesinin büyük rakamı (en çarpıcı kare). Üst bandı
karartıp başlığı (sarı vurgulu son kelimeler) basar. CPU/PIL, VRAM'e dokunmaz.

Kullanım:  python tools/make_short_thumb.py <job_id> <idx> ["Başlık"]
Çıktı:     output/<job_id>/reel_<idx>_thumb.jpg
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.utils.paths import job_path  # noqa: E402
from tools.make_thumbnail import GOLD, WHITE, _draw_text_outlined, _fit_text  # noqa: E402

W, H = 1080, 1920


def make(job_id: str, idx: int, title: str, at: float = 2.0) -> Path:
    reel = job_path(job_id, f"reel_{idx}.mp4")
    frame = job_path(job_id, f"reel_{idx}_thumbframe.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(reel), "-frames:v", "1", str(frame)], check=True)
    img = Image.open(frame).convert("RGB").resize((W, H))


    d = ImageDraw.Draw(img)
    text = title.replace("#Shorts", "").replace("#shorts", "").strip().replace("i", "İ").replace("ı", "I").upper()
    font, lines = _fit_text(d, text, W - 120, 3, 100, 60)
    lh = int(font.size * 1.12)
    y = 1385 - len(lines) * lh  # Stamp rakamı ile alt altyazı kutusu arasındaki boş alan
    for i, ln in enumerate(lines):
        # son satır altın sarısı (merak/vurgu), diğerleri beyaz
        _draw_text_outlined(d, (W // 2, y + i * lh), ln, font, GOLD if i == len(lines) - 1 and len(lines) > 1 else WHITE,
                            ow=7, anchor="ma")

    out = job_path(job_id, f"reel_{idx}_thumb.jpg")
    img.save(out, "JPEG", quality=90)
    frame.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    import json
    jid, i = sys.argv[1], int(sys.argv[2])
    t = sys.argv[3] if len(sys.argv) > 3 else json.loads(job_path(jid, "reels.json").read_text(encoding="utf-8"))[i - 1]["title"]
    print(make(jid, i, t))

"""Profesyonel YouTube kapak (thumbnail) üreticisi — CPU/PIL, GPU/render'a dokunmaz.

Bir işin video karesinden (sunucu görünür) yola çıkıp üstüne büyük, okunaklı Türkçe
başlık + "BU HAFTA" rozeti + hafif karartma/gradient bindirir. Yüksek CTR için tasarım:
kalın beyaz başlık + koyu kontur, altın-sarısı vurgu şeridi.

Kullanım:
    python tools/make_thumbnail.py <job_id> ["Ust satir"] ["Alt satir (sari)"]
    # başlık verilmezse metadata.json'daki title kullanılır.
Çıktı: output/_videos/<job_id>_thumb.jpg  (1280x720)
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.utils.paths import job_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 720
GOLD = (245, 197, 66)
WHITE = (255, 255, 255)
SHADOW = (0, 0, 0)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold
    r"C:\Windows\Fonts\ariblk.ttf",     # Arial Black
    r"C:\Windows\Fonts\arialbd.ttf",    # Arial Bold
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _frame(job_id: str) -> Image.Image:
    """Kapak arka planı için TEMİZ bir görsel arar (altyazı/metin İÇERMEYEN): önce s04'ün
    ürettiği visuals/ klasöründeki SDXL foto-gerçekçi görsellerden birini kullanır (aynı
    "temiz arka plan" mantığı pipeline/web/app.py::_preview_background'da da kullanılıyor).
    Video karesinden kırpma SON ÇARE'dir -- final video.mp4'te animasyonlu altyazı sürekli
    ekranda olduğu için hangi saniye seçilirse seçilsin metin/kelime bindirmesi kapağa karışır."""
    vis_dir = job_path(job_id, "visuals")
    if vis_dir.is_dir():
        imgs = sorted(p for p in vis_dir.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
        if imgs:
            return Image.open(imgs[0]).convert("RGB").resize((W, H))

    import subprocess
    vid = ROOT / "output" / "_videos" / f"{job_id}.mp4"
    if not vid.exists():
        vid = ROOT / "output" / job_id / "video.mp4"
    out = ROOT / "output" / "_videos" / f"{job_id}_thumbframe.png"
    if vid.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "3", "-i", str(vid), "-frames:v", "1", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if out.exists():
            return Image.open(out).convert("RGB").resize((W, H))
    # yedek: avatar fotoğrafı
    photo = ROOT / "assets" / "avatar" / "photo.png"
    if photo.exists():
        return Image.open(photo).convert("RGB").resize((W, H))
    return Image.new("RGB", (W, H), (20, 22, 28))


def _draw_text_outlined(draw, xy, text, font, fill, outline=SHADOW, ow=6, anchor="la"):
    x, y = xy
    for dx in range(-ow, ow + 1, 2):
        for dy in range(-ow, ow + 1, 2):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline, anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def _wrap_lines(draw, text, font, max_width) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_text(draw, text, max_width, max_lines, start_size, min_size, step=4):
    """1280px genişliğe taşan başlıkların kesilmesini önler (bkz. 17 Eyl bug -- uzun
    başlıklar kenardan taşıp kırpılıyordu): satıra sığdırır, sığmıyorsa max_lines'a
    ulaşana kadar font küçültülür. En kötü ihtimalde min_size'da bile taşarsa fazla
    satırlar kırpılır (hiçbir zaman kod hatası vermez, sadece görsel olarak kısalır)."""
    size = start_size
    while size >= min_size:
        font = _font(size)
        lines = _wrap_lines(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
        size -= step
    font = _font(min_size)
    return font, _wrap_lines(draw, text, font, max_width)[:max_lines]


def make(job_id: str, top_line: str | None, bottom_line: str | None):
    base = _frame(job_id)

    # sol taraftan sağa koyu gradient (metin okunaklı olsun) + alt karartma
    grad = Image.new("L", (W, 1))
    for x in range(W):
        grad.putpixel((x, 0), int(200 * max(0, 1 - x / (W * 0.75))))
    grad = grad.resize((W, H))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    base = Image.composite(dark, base, grad)
    # alt şerit karartma
    bottom = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(bottom)
    bd.rectangle([0, int(H * 0.72), W, H], fill=150)
    bottom = bottom.filter(ImageFilter.GaussianBlur(40))
    base = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), base, bottom)

    draw = ImageDraw.Draw(base)

    # "BU HAFTA" rozeti (altın şerit)
    badge_font = _font(40)
    bx, by = 60, 60
    btext = "BU HAFTA"
    tb = draw.textbbox((0, 0), btext, font=badge_font)
    draw.rectangle([bx - 18, by - 10, bx + (tb[2] - tb[0]) + 18, by + (tb[3] - tb[1]) + 22], fill=GOLD)
    draw.text((bx, by), btext, font=badge_font, fill=(20, 20, 20))

    # metin: metadata'dan al ya da parametre
    if not top_line:
        meta_f = ROOT / "output" / job_id / "metadata.json"
        title = ""
        if meta_f.exists():
            try:
                title = json.loads(meta_f.read_text(encoding="utf-8")).get("title", "")
            except Exception:
                pass
        top_line = title or "ALTIN ve GÜMÜŞ"
        bottom_line = bottom_line or "Bu hafta ne oldu?"

    top_line = top_line.upper()
    max_text_width = W - 120  # 60px kenar boşluğu her iki tarafta
    tfont, title_lines = _fit_text(draw, top_line, max_text_width, max_lines=2,
                                    start_size=88, min_size=44)
    ty = 235
    line_height = int(tfont.size * 1.08)
    for line in title_lines:
        _draw_text_outlined(draw, (60, ty), line, tfont, WHITE, ow=6)
        ty += line_height

    if bottom_line:
        bfont, bottom_lines = _fit_text(draw, bottom_line, max_text_width, max_lines=1,
                                         start_size=72, min_size=36)
        _draw_text_outlined(draw, (60, ty + 20), bottom_lines[0], bfont, GOLD, ow=6)

    dst = ROOT / "output" / "_videos" / f"{job_id}_thumb.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    base.save(dst, quality=92)
    print(f"Kapak yazıldı -> {dst}")
    return dst


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("kullanım: python tools/make_thumbnail.py <job_id> [ust] [alt]")
    make(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None,
         sys.argv[3] if len(sys.argv) > 3 else None)

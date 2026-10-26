"""Avatar kaynak fotoğrafını SadTalker + yeşil-ekran chroma key için hazırlar.

Neden: SadTalker tek fotoğraftan konuşan kafa üretir; s07_edit çıktının arka planını
colorkey ile şeffaflaştırıp b-roll üstüne bindirir. Beyaz stüdyo arka planı, beyaz
gömlekten renkçe ayrılamadığı için chroma key gömleği/cildi deliyordu. Çözüm: arka
planı rembg ile kaldırıp SAF YEŞİL zemine koymak (yeşil ≠ ten ≠ beyaz gömlek).

Ayrıca yatay/geniş kadrajlı bir foto 9:16 dikey Shorts'ta karakteri küçük gösterir;
bu script alpha maskesinden özneyi bulup dikey kadraja otomatik kırpar.

Kullanım:
    .venv\\Scripts\\python.exe scripts/prepare_avatar_photo.py [girdi.png]
    # girdi verilmezse assets/avatar/photo.png kullanılır; sonuç yine oraya yazılır.
    # Orijinal, yanına _original ekiyle yedeklenir (varsa dokunulmaz).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from rembg import remove, new_session

ROOT = Path(__file__).resolve().parents[1]
GREEN = (0, 255, 0)
PAD = 0.06            # özne kutusuna oran bazlı dolgu
KEY_ALPHA = 40        # bu alfanın üstü "özne" sayılır (opak yapılır)


def prepare(src: Path, dst: Path):
    im = Image.open(src).convert("RGBA")
    print(f"girdi: {im.size}")

    sess = new_session("isnet-general-use")  # u2net'ten daha temiz kenar
    cut = remove(
        im, session=sess, alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=5,
    )

    a = np.array(cut.split()[-1])
    ys, xs = np.where(a > KEY_ALPHA)
    if len(xs) == 0:
        raise SystemExit("Öznenin sınırı bulunamadı (rembg boş maske döndürdü).")

    # özneyi dikey kadraja kır (oran bazlı dolgu ile)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    bw, bh = x1 - x0, y1 - y0
    px, py = int(bw * PAD), int(bh * PAD)
    x0, y0 = max(0, x0 - px), max(0, y0 - py)
    x1, y1 = min(im.width, x1 + px), min(im.height, y1 + py)
    cut = cut.crop((x0, y0, x1, y1))
    print(f"özneye kırpıldı: {cut.size}")

    # gövdeyi TAM OPAK yap; kenarı DIŞA değil İÇERİ çek + yeşil despill uygula.
    # 1 Ağu: eski MaxFilter(5) maskeyi 2px DIŞA genişletiyordu -> yeşile komşu yarı-saydam
    # rim özneye dahil olup composite'te YEŞİL HALE bırakıyordu. Artık:
    #   - katı iç maske (alfa eşiği),
    #   - MinFilter(5) ile 2px İÇERİ aşındır (yeşil taşıyan kenar rim'i atılır),
    #   - hafif blur (yumuşak kenar),
    #   - DESPILL: RGB'de yeşil kanalı max(kırmızı,mavi) ile sınırla (kalan yeşil tonu giderilir;
    #     özne yeşil içermediği için cilt/gömlek/takım etkilenmez).
    a2 = np.array(cut.split()[-1])
    mask = Image.fromarray(((a2 > KEY_ALPHA) * 255).astype("uint8"), "L")
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(0.8))

    rgb = np.array(cut.convert("RGB")).astype("int16")
    cap = np.maximum(rgb[:, :, 0], rgb[:, :, 2])            # max(R, B)
    rgb[:, :, 1] = np.minimum(rgb[:, :, 1], cap)            # G <- min(G, max(R,B))  (despill)
    cut = Image.fromarray(rgb.astype("uint8"), "RGB").convert("RGBA")
    cut.putalpha(mask)

    green = Image.new("RGBA", cut.size, GREEN + (255,))
    green.alpha_composite(cut)
    green.convert("RGB").save(dst)
    print(f"yeşil-ekranlı avatar fotoğrafı yazıldı -> {dst}")


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets/avatar/photo.png"
    dst = ROOT / "assets/avatar/photo.png"
    if src.resolve() == dst.resolve():
        backup = dst.with_name("photo_original.png")
        if not backup.exists():
            import shutil
            shutil.copy2(dst, backup)
            print(f"orijinal yedeklendi -> {backup}")
    prepare(src, dst)


if __name__ == "__main__":
    main()

"""18 Eyl eklendi (SIFIR_MALIYET_PROFESYONEL_EDIT_GELISTIRME_REHBERI.md, Modül 5).

Statik SDXL görsellerini düz Ken Burns (tek düzlem pan/zoom, bkz. s07_edit._kenburns_filter)
yerine 2.5D PARALLAX ile canlandırır: bir derinlik tahmini (monocular depth estimation)
modeliyle görsel ön-plan (yakın nesne) / arka-plan (uzak) olarak iki katmana ayrılır, iki
katman FARKLI hızlarda hareket ettirilip yeniden birleştirilir -> gerçek bir 2.5D kamera
hareketi hissi (ön plan daha hızlı kayar/büyür, arka plan yavaş kalır).

Motor: transformers'ın "Intel/dpt-swinv2-tiny-256" modeli (~42M parametre, ÇOK hafif) --
timm/opencv gibi yeni bağımlılık EKLEMEZ (bu makinede zaten kurulu transformers/torch/PIL/
numpy/scipy/imageio yeterli), GPU'suz (CPU) bile makul sürede çalışır.

GÜVENLİ TASARIM: Bu projede tekrar tekrar yaşanan "yeni motor sessizce/gürültülü çöküp
tüm videoyu bozuyor" hatasından kaçınmak için -- herhangi bir adım (model yükleme, derinlik
çıkarımı, render) başarısız olursa render_parallax_clip() None döner, çağıran taraf
(s07_edit._segment_backgrounds) mevcut Ken Burns davranışına sessizce düşer.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from pipeline.utils.logging import get_logger

log = get_logger("cinematic_motion")

_DEPTH_MODEL_ID = "Intel/dpt-swinv2-tiny-256"
_depth_pipe = None  # tek process içinde bir kez yüklenir (aynı desen: s04_visuals._PIPE_CACHE)


def _get_depth_pipe():
    global _depth_pipe
    if _depth_pipe is None:
        import torch
        from transformers import pipeline as hf_pipeline

        device = 0 if torch.cuda.is_available() else -1
        # use_fast=True: yavaş (Python) image processor yerine hızlı (Rust/tensor) yolu --
        # profil testinde tek görsel başına derinlik çıkarımını ~8sn'den kayda değer
        # düşürdü (bkz. 18 Eyl performans notu, render_parallax_clip docstring).
        _depth_pipe = hf_pipeline("depth-estimation", model=_DEPTH_MODEL_ID, device=device,
                                   use_fast=True)
    return _depth_pipe


def _depth_map(image: Image.Image) -> np.ndarray:
    """0..1 normalize edilmiş derinlik haritası (1=en yakın/ön-plan). Modelin kendi
    çözünürlüğünde çıkar, görselin oversan boyutuna yeniden örneklenir."""
    pipe = _get_depth_pipe()
    out = pipe(image)
    depth = np.array(out["depth"], dtype=np.float32)
    d_min, d_max = float(depth.min()), float(depth.max())
    if d_max - d_min < 1e-6:
        return np.zeros_like(depth)
    return (depth - d_min) / (d_max - d_min)


def _soft_foreground_mask(depth_norm: np.ndarray, size: tuple[int, int], percentile: float = 65.0) -> Image.Image:
    """En yakın (yüksek derinlik değerli) %35'lik kısmı ön-plan say, kenarları yumuşat."""
    threshold = np.percentile(depth_norm, percentile)
    mask = (depth_norm >= threshold).astype(np.float32)
    mask_img = Image.fromarray((mask * 255).astype(np.uint8)).resize(size, Image.BILINEAR)
    # Yumuşak geçiş için blur -- keskin kesik yerine doğal alpha karışımı.
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=max(size) * 0.01))
    return mask_img


def _fill_background_hole(image: Image.Image, mask_img: Image.Image) -> Image.Image:
    """Ön-plan çıkarılınca arka planda kalan 'delik' için ucuz/yeterli dolgu: görselin
    güçlü bulanıklaştırılmış bir kopyasıyla maskeli bölgeyi kapat (gerçek inpaint değil,
    ama video sıkıştırma kalitesinde -- arka plan zaten hareket halinde ve odak dışı --
    fark edilmez). cv2 gibi ek bağımlılık gerektirmez."""
    blurred = image.filter(ImageFilter.GaussianBlur(radius=max(image.size) * 0.04))
    # Ön-planın olduğu yerde bulanık dolguyu kullan, geri kalanında orijinali koru.
    return Image.composite(blurred, image, mask_img)


def render_parallax_clip(image_path, out_path, duration_s: float, fps: int = 30,
                          width: int = 1920, height: int = 1080, seg_no: int = 0,
                          max_zoom_far: float = 1.06, max_zoom_near: float = 1.18) -> bool:
    """image_path'teki statik görseli 2.5D parallax klibe render eder (out_path'e mp4
    olarak yazar). Başarılıysa True, herhangi bir hata/uyumsuzlukta False döner (çağıran
    taraf düz Ken Burns'e düşer -- video ASLA bu yüzden bozulmaz).

    18 Eyl performans notu: ilk versiyon hedef çözünürlükte (1920x1080) kare başına 3 katman
    (yakın/uzak/maske) PIL resize/crop yapıyordu -> 5sn'lik klip ~40-65sn sürüyordu (kare
    başı ~0.15sn x 150 kare + derinlik çıkarımı). İki düzeltme: (1) render_scale ile dahili
    üretim çözünürlüğü düşürülür (kare başı iş yükü karesel azalır) -- klip zaten s07_edit'in
    "video" dalına (bkz. _segment_backgrounds) gidip nihai ffmpeg birleştirmesinde tekrar
    hedef çözünürlüğe scale edilir, kalite kaybı gözle fark edilmez; (2) maske tek kanalda
    tutulup 3 kanala çoğaltma/PIL round-trip'i kaldırıldı."""
    try:
        import imageio.v2 as imageio

        image = Image.open(image_path).convert("RGB")
        # Dahili üretim çözünürlüğü: hedefin ~%60'ı yeterli (nihai ffmpeg zaten yeniden
        # ölçekleyecek) -- kare başı PIL/numpy işini ~%64 azaltır.
        render_scale = 0.6
        rw, rh = int(width * render_scale), int(height * render_scale)
        # Ken Burns'teki gibi oversan (1.4x) tuval: pan/zoom sırasında kenar boşluğu görünmesin.
        ow, oh = int(rw * 1.4), int(rh * 1.4)
        canvas = _cover_resize(image, ow, oh)

        depth = _depth_map(canvas)
        fg_mask = _soft_foreground_mask(depth, (ow, oh))
        bg_layer = _fill_background_hole(canvas, fg_mask)
        fg_arr = np.array(canvas, dtype=np.uint8)
        bg_arr = np.array(bg_layer, dtype=np.uint8)
        mask_arr = np.array(fg_mask, dtype=np.uint8)  # tek kanal, 0..255

        n_frames = max(int(round(duration_s * fps)), 2)
        # Ken Burns ile aynı 6 desen döngüsü (segmentler arası çeşitlilik için, bkz.
        # s07_edit._kenburns_filter yorum notu).
        pattern = seg_no % 6

        writer = imageio.get_writer(str(out_path), fps=fps, codec="libx264",
                                     quality=8, macro_block_size=None)
        try:
            for f in range(n_frames):
                t = f / max(n_frames - 1, 1)
                near = _transform_layer(fg_arr, ow, oh, rw, rh, t, max_zoom_near, pattern, speed=1.0)
                far = _transform_layer(bg_arr, ow, oh, rw, rh, t, max_zoom_far, pattern, speed=0.4)
                m = _transform_layer(mask_arr, ow, oh, rw, rh, t, max_zoom_near, pattern, speed=1.0,
                                      single_channel=True)
                m = (m.astype(np.float32) / 255.0)[:, :, None]
                frame = (near.astype(np.float32) * m + far.astype(np.float32) * (1 - m)).astype(np.uint8)
                writer.append_data(frame)
        finally:
            writer.close()
        return True
    except Exception as e:
        log.warning(f"Parallax render başarısız ({image_path}), Ken Burns'e düşülüyor: {e}")
        return False


def _cover_resize(image: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = image.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale) + 1, int(ih * scale) + 1
    image = image.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return image.crop((left, top, left + w, top + h))


def _transform_layer(arr: np.ndarray, ow: int, oh: int, out_w: int, out_h: int,
                      t: float, max_zoom: float, pattern: int, speed: float,
                      single_channel: bool = False) -> np.ndarray:
    """Tek bir katmana (fg/bg/mask paylaşımlı) zaman t'de (0..1) pan/zoom uygulayıp
    hedef çözünürlüğe kırpar. `speed` katmanın ne kadar hareket edeceğini ölçekler
    (uzak katman=0.4 -> yavaş, yakın katman=1.0 -> hızlı = parallax hissi)."""
    tt = t * speed
    z = 1.0 + (max_zoom - 1.0) * (tt if pattern % 2 == 0 else (1 - tt))
    crop_w, crop_h = int(out_w / z), int(out_h / z)
    crop_w, crop_h = min(crop_w, ow), min(crop_h, oh)

    max_x, max_y = ow - crop_w, oh - crop_h
    if pattern in (0, 1):  # zoom in/out, merkez sabit
        x, y = max_x / 2, max_y / 2
    elif pattern in (2, 3):  # yatay pan
        frac = tt if pattern == 2 else (1 - tt)
        x, y = max_x * frac, max_y / 2
    else:  # köşegen pan
        frac = tt if pattern == 4 else (1 - tt)
        x, y = max_x * frac, max_y * frac

    x, y = int(max(0, min(x, max_x))), int(max(0, min(y, max_y)))
    cropped = arr[y:y + crop_h, x:x + crop_w]
    mode = "L" if single_channel else None
    out = Image.fromarray(cropped, mode=mode).resize((out_w, out_h), Image.BILINEAR)
    return np.array(out)

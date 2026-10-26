"""Sentez SFX kütüphanesi (30 Eyl): lisans derdi olmayan, finans yayını tonunda (yumuşak, abartısız) ses efektleri.
Her kategoride 2-4 varyant -> aynı ses art arda tekrar etmez. Çıktı: assets/sfx/ + remotion/public/sfx/ (48 kHz stereo wav).

  python scripts/gen_sfx.py
"""
import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "sfx"
PUB = ROOT / "remotion" / "public" / "sfx"
SR = 48000
rng = np.random.default_rng(20260930)


def t(dur):
    return np.arange(int(SR * dur)) / SR


def env(n, a=0.005, d=0.3, shape=4.0):
    """Hızlı atak + üstel sönüm."""
    x = np.arange(n) / SR
    att = np.clip(x / max(a, 1e-4), 0, 1)
    return att * np.exp(-shape * np.clip(x - a, 0, None) / max(d, 1e-4))


def bp(x, lo, hi, order=4):
    return sosfilt(butter(order, [lo, hi], "bandpass", fs=SR, output="sos"), x)


def lp(x, f, order=4):
    return sosfilt(butter(order, f, "lowpass", fs=SR, output="sos"), x)


def hp(x, f, order=4):
    return sosfilt(butter(order, f, "highpass", fs=SR, output="sos"), x)


def reverb(x, dur=0.8, mix=0.18):
    n = int(SR * dur)
    ir = rng.standard_normal(n) * np.exp(-6 * np.arange(n) / n)
    ir = lp(ir, 6000)
    wet = np.convolve(x, ir)[: len(x) + n // 2]
    wet /= np.max(np.abs(wet)) + 1e-9
    y = np.concatenate([x, np.zeros(len(wet) - len(x))])
    return (1 - mix) * y + mix * wet * np.max(np.abs(x))


def stereo(x, width=0.12):
    d = int(SR * 0.004 * width / 0.12)
    r = np.concatenate([np.zeros(d), x])[: len(x)]
    return np.stack([x, (1 - width) * x + width * r], axis=1)


def norm(x, peak=0.8):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def fade(x, fin=0.003, fout=0.02):
    n = len(x)
    a, b = int(SR * fin), int(SR * fout)
    w = np.ones(n)
    w[:a] = np.linspace(0, 1, a)
    w[n - b:] = np.linspace(1, 0, b)
    return x * w


def sweep(f0, f1, dur, curve=2.0):
    tt = t(dur)
    f = f0 + (f1 - f0) * (tt / dur) ** curve
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


# ---------------------------------------------------------------- sesler
def whoosh(dur, lo0, hi0, lo1, hi1, peak_at=0.55):
    """Filtre süpürmeli gürültü: geçişler."""
    n = int(SR * dur)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    steps = 40
    for k in range(steps):
        a, b = k * n // steps, (k + 1) * n // steps
        q = k / steps
        lo = lo0 + (lo1 - lo0) * q
        hi = hi0 + (hi1 - hi0) * q
        seg = bp(noise, lo, hi, 2)[a:b]
        out[a:b] = seg
    x = np.arange(n) / n
    shape = np.where(x < peak_at, (x / peak_at) ** 2, ((1 - x) / (1 - peak_at)) ** 1.5)
    return reverb(out * shape, 0.5, 0.15)


def riser(dur=1.6):
    """Gerilim yükselişi (bölüm/sonuç öncesi)."""
    tt = t(dur)
    tone = sweep(120, 900, dur, 2.2) * 0.35 + sweep(240, 1800, dur, 2.2) * 0.15
    noise = hp(rng.standard_normal(len(tt)), 2500) * (tt / dur) ** 2 * 0.5
    e = (tt / dur) ** 1.6
    return reverb((tone + noise) * e, 0.6, 0.2)


def downer(dur=1.2):
    """Düşüş (grafik aşağı, kayıp)."""
    tt = t(dur)
    tone = sweep(700, 90, dur, 0.6)
    return reverb(tone * env(len(tt), 0.01, dur * 0.6, 2.5) * 0.7 + lp(rng.standard_normal(len(tt)), 800) * env(len(tt), 0.005, 0.2) * 0.3, 0.6, 0.2)


def impact(freq=48, dur=1.4, click=0.35):
    """Derin vuruş (rakam oturduğunda)."""
    tt = t(dur)
    f = freq * (1 + 1.8 * np.exp(-tt * 30))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(tt), 0.002, 0.35, 3)
    ck = hp(rng.standard_normal(len(tt)), 3000) * env(len(tt), 0.0005, 0.012, 5) * click
    return reverb(body + ck, 0.9, 0.12)


def tick(freq=2400, dur=0.05):
    tt = t(dur)
    return (np.sin(2 * np.pi * freq * tt) * 0.6 + hp(rng.standard_normal(len(tt)), 4000) * 0.4) * env(len(tt), 0.0003, 0.01, 6)


def ticks(n=10, gap=0.055, jitter=0.0, freq=2400):
    """Sayaç tıkırtısı: rakamlar dönerken."""
    out = np.zeros(int(SR * (n * gap + 0.1)))
    for k in range(n):
        s = int(SR * (k * gap * (1 + 0.6 * k / n)))  # yavaşlayan
        tk = tick(freq * (1 + 0.02 * rng.standard_normal()), 0.04) * (0.5 + 0.5 * (1 - k / n))
        out[s:s + len(tk)] += tk[: len(out) - s]
    return out


def reverse_swell(dur=1.3):
    """Ters dalga -> bölüm kartı girişinde emme etkisi."""
    tt = t(dur)
    chord = sum(np.sin(2 * np.pi * f * tt) for f in (110, 165, 220, 330)) / 4
    x = reverb(chord * env(len(tt), 0.01, 0.8, 2.5), 1.0, 0.45)
    return x[::-1]


def alert(dur=0.9):
    """Son dakika: iki tonlu yumuşak uyarı."""
    a = np.concatenate([np.sin(2 * np.pi * 880 * t(0.14)) * env(int(SR * 0.14), 0.004, 0.1, 2),
                        np.zeros(int(SR * 0.05)),
                        np.sin(2 * np.pi * 660 * t(0.22)) * env(int(SR * 0.22), 0.004, 0.16, 2)])
    a = a + 0.25 * np.concatenate([np.sin(2 * np.pi * 1760 * t(0.14)) * env(int(SR * 0.14), 0.004, 0.06), np.zeros(len(a) - int(SR * 0.14))])
    return reverb(a, 0.7, 0.25)


def chime(notes=(523.25, 659.25, 783.99), gap=0.09):
    """Olumlu vurgu (yükseliş, sonuç)."""
    out = np.zeros(int(SR * (gap * len(notes) + 1.4)))
    for k, f in enumerate(notes):
        tt = t(1.3)
        tone = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt) + 0.1 * np.sin(2 * np.pi * 3.01 * f * tt)) * env(len(tt), 0.003, 0.5, 3)
        s = int(SR * k * gap)
        out[s:s + len(tone)] += tone
    return reverb(out, 1.0, 0.3)


def metal_ring(dur=2.0, base=620):
    """Metal/sikke çınlaması (altın/gümüş sahneleri): FM + inharmonik kısmi tonlar."""
    tt = t(dur)
    x = sum(a * np.sin(2 * np.pi * base * r * tt + 0.8 * np.sin(2 * np.pi * base * 1.41 * tt)) * np.exp(-tt * d)
            for a, r, d in ((1, 1, 2.5), (0.5, 2.76, 3.5), (0.3, 5.4, 5), (0.2, 8.93, 7)))
    ck = hp(rng.standard_normal(len(tt)), 5000) * env(len(tt), 0.0003, 0.008, 5) * 0.6
    return reverb(x + ck, 1.2, 0.25)


def typewriter(n=14, gap=0.085):
    out = np.zeros(int(SR * (n * gap + 0.2)))
    for k in range(n):
        s = int(SR * (k * gap + 0.02 * rng.random()))
        c = bp(rng.standard_normal(int(SR * 0.03)), 1500, 6000) * env(int(SR * 0.03), 0.0005, 0.008, 5)
        c += np.sin(2 * np.pi * 180 * t(0.03)) * env(int(SR * 0.03), 0.001, 0.01) * 0.4
        out[s:s + len(c)] += c * (0.7 + 0.3 * rng.random())
    return out


def blips(n=6, gap=0.07, base=900):
    """Veri blipleri (ısı haritası, kartlar açılırken)."""
    out = np.zeros(int(SR * (n * gap + 0.3)))
    for k in range(n):
        f = base * (2 ** (rng.integers(0, 7) / 12))
        b = np.sin(2 * np.pi * f * t(0.06)) * env(int(SR * 0.06), 0.002, 0.03, 4)
        s = int(SR * k * gap)
        out[s:s + len(b)] += b
    return reverb(out, 0.4, 0.2)


def data_sweep(dur=1.0):
    """Grafik çizilirken yumuşak dijital süpürme."""
    tt = t(dur)
    tone = sweep(300, 1200, dur, 1.2) * 0.25
    shimmer = bp(rng.standard_normal(len(tt)), 3000, 9000) * 0.15
    e = np.sin(np.pi * tt / dur) ** 1.5
    return reverb((tone + shimmer) * e, 0.5, 0.2)


def glitch(dur=0.35):
    n = int(SR * dur)
    x = np.zeros(n)
    k = 0
    while k < n:
        L = int(SR * rng.uniform(0.008, 0.03))
        f = rng.uniform(200, 3000)
        seg = np.sign(np.sin(2 * np.pi * f * np.arange(L) / SR)) * 0.3 if rng.random() < 0.5 else rng.standard_normal(L) * 0.3
        m = min(L, n - k)
        x[k:k + m] = seg[:m]
        k += L + int(SR * rng.uniform(0, 0.02))
    return bp(x, 300, 7000) * env(n, 0.001, dur * 0.8, 1.5)


def heartbeat():
    b = impact(38, 0.5, 0.05)
    out = np.zeros(int(SR * 1.2))
    out[: len(b)] += b
    s = int(SR * 0.28)
    out[s:s + len(b)] += 0.7 * b[: len(out) - s]
    return out


def paper(dur=0.6):
    n = int(SR * dur)
    x = bp(rng.standard_normal(n), 1200, 8000) * env(n, 0.02, 0.25, 2)
    x *= 1 + 0.6 * np.sin(2 * np.pi * 23 * t(dur)) ** 2
    return x


def ui_pop(f=660):
    tt = t(0.25)
    x = np.sin(2 * np.pi * np.cumsum(f * (1 + 0.6 * np.exp(-tt * 40))) / SR) * env(len(tt), 0.001, 0.07, 3)
    return reverb(x, 0.3, 0.15)


def steps(freqs, gap=0.075):
    """9 Eki: yönlü nota basamakları (yükseliş: majör yukarı, düşüş: minör aşağı)."""
    out = np.zeros(int(SR * (gap * len(freqs) + 0.4)))
    for i, f in enumerate(freqs):
        tt = t(0.3)
        x = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * env(len(tt), 0.002, 0.12, 3)
        st = int(i * gap * SR)
        out[st:st + len(x)] += x * (0.75 + 0.25 * i / len(freqs))
    return reverb(out, 0.5, 0.2)


def pitch_whoosh(f0, f1, dur=0.7):
    """9 Eki: tonlu süpürme + hava (fiyat 'düştü/fırladı' anı)."""
    n = int(SR * dur)
    tone = np.sin(2 * np.pi * np.cumsum(sweep(f0, f1, dur, 1.5)[:n]) / SR) * env(n, 0.03, dur * 0.6, 2)
    air = bp(rng.standard_normal(n), 400, 5000) * env(n, 0.1, dur * 0.5, 2) * 0.35
    return reverb(tone * 0.7 + air, 0.6, 0.18)


def number_lock():
    """9 Eki: rakam yerine oturduğunda kısa klik + alçak gövde."""
    tt = t(0.4)
    click = bp(rng.standard_normal(len(tt)), 2500, 9000) * np.exp(-tt * 300)
    body = np.sin(2 * np.pi * (90 + 120 * np.exp(-tt * 40)) * tt) * np.exp(-tt * 12)
    return click * 0.6 + body


SOUNDS = {
    # 9 Eki: yön sesleri
    "rise_steps": lambda: steps((523.25, 659.25, 783.99, 1046.5)),
    "fall_steps": lambda: steps((783.99, 622.25, 523.25, 392.0), 0.09),
    "lift_whoosh": lambda: pitch_whoosh(180, 720, 0.7),
    "drop_whoosh": lambda: pitch_whoosh(700, 140, 0.8),
    "number_lock": number_lock,
    # geçişler (varyantlar)
    "whoosh_soft_1": lambda: whoosh(0.6, 200, 1200, 1500, 6000),
    "whoosh_soft_2": lambda: whoosh(0.7, 300, 1600, 800, 4000, 0.45),
    "whoosh_air_1": lambda: whoosh(1.0, 150, 800, 2000, 9000, 0.6),
    "whoosh_air_2": lambda: whoosh(0.9, 2000, 8000, 200, 1500, 0.4),
    "swipe_1": lambda: whoosh(0.3, 1000, 5000, 3000, 12000, 0.35),
    "swipe_2": lambda: whoosh(0.28, 3000, 12000, 800, 4000, 0.3),
    # gerilim / yön
    "riser_1": lambda: riser(1.6),
    "riser_2": lambda: riser(1.1),
    "downer_1": lambda: downer(1.2),
    "downer_2": lambda: downer(0.8),
    "reverse_swell": lambda: reverse_swell(1.3),
    # vurgular
    "impact_deep_1": lambda: impact(44, 1.4, 0.35),
    "impact_deep_2": lambda: impact(52, 1.1, 0.2),
    "impact_tight": lambda: impact(70, 0.6, 0.5),
    "heartbeat": heartbeat,
    "chime_up": lambda: chime((523.25, 659.25, 783.99)),
    "chime_soft": lambda: chime((587.33, 739.99), 0.12),
    "chime_down": lambda: chime((783.99, 622.25, 523.25)),
    # sahneye özel
    "counter_ticks": lambda: ticks(12, 0.05),
    "counter_ticks_short": lambda: ticks(6, 0.06, freq=2000),
    "data_sweep_1": lambda: data_sweep(1.0),
    "data_sweep_2": lambda: data_sweep(1.4),
    "blips": lambda: blips(6),
    "blips_low": lambda: blips(5, 0.09, 520),
    "alert_breaking": lambda: alert(),
    "metal_ring_gold": lambda: metal_ring(2.0, 620),
    "metal_ring_silver": lambda: metal_ring(1.8, 880),
    "typewriter": lambda: typewriter(14),
    "glitch": lambda: glitch(),
    "paper_flip": lambda: paper(0.6),
    "ui_pop_1": lambda: ui_pop(660),
    "ui_pop_2": lambda: ui_pop(880),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PUB.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])  # 9 Eki: ad verilirse yalnız onlar üretilir (mevcut seslere dokunmaz)
    for name, fn in SOUNDS.items():
        if only and name not in only:
            continue
        x = fade(norm(fn(), 0.8))
        y = stereo(x)
        p = OUT / f"{name}.wav"
        sf.write(str(p), y.astype(np.float32), SR, subtype="PCM_16")
        shutil.copy(p, PUB / p.name)
    print(f"{len(SOUNDS)} ses -> {OUT} + {PUB}")


if __name__ == "__main__":
    main()

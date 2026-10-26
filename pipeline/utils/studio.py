"""Profesyonel "stüdyo" görünümü için son-aşama ffmpeg filtre yardımcıları.

s07_edit montajın SONUNDA (altyazı yakılmadan ÖNCE) uygulanır: hafif sinematik renk
grade + kenar vinyeti + ince keskinlik -> ham render yerine "profesyonel stüdyodan çıkmış"
his. Altyazıdan ÖNCE uygulanır ki beyaz altyazı grade'den etkilenip griye kaymasın.

config.yaml edit.studio_look: true|false (varsayılan true) ile açılır/kapanır.
Değerler bilinçli olarak HAFİF: abartılı grade "yapay/Instagram filtresi" hissi verir.
"""

# Hafif sinematik grade: kontrast +, doygunluk +, çok hafif sıcaklık; kenarda yumuşak vinyet;
# ince unsharp (netlik). Hepsi ölçülü — foto-gerçekçiliği bozmadan "prodüksiyon" hissi katar.
_DEFAULT = {
    "contrast": 1.06,
    "saturation": 1.08,
    "brightness": 0.01,
    "gamma": 1.00,
    "vignette": True,       # kenarları hafif karart -> göz merkeze (sunucuya) odaklanır
    "vignette_angle": "PI/5",
    "sharpen": True,        # ince unsharp -> HD netlik
}


def studio_filter(style: dict | None = None) -> str:
    """Bir '[in]...[out]' değil, ARADAKİ filtre zincirini döner (virgülle bağlanır);
    çağıran taraf [label] önüne/sonuna ekler. Boş string dönerse (kapalı) atlanır."""
    s = dict(_DEFAULT)
    if style:
        s.update({k: v for k, v in style.items() if v is not None})

    parts = [
        f"eq=contrast={s['contrast']}:saturation={s['saturation']}"
        f":brightness={s['brightness']}:gamma={s['gamma']}"
    ]
    if s.get("sharpen"):
        # hafif keskinlik (luma), gürültü üretmeyecek kadar düşük
        parts.append("unsharp=5:5:0.5:5:5:0.0")
    if s.get("vignette"):
        parts.append(f"vignette=angle={s['vignette_angle']}")
    return ",".join(parts)

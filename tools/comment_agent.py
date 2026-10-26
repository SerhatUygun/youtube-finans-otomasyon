"""10 Eki: yorum cevap ajanı — kanaldaki yeni yorumları çeker, Claude kanal üslubunda cevap yazar.
Güvenli ve net cevaplar otomatik gönderilir; emin olunamayanlar output/_brain/comment_review.json'a (onay kuyruğu) düşer.
Kurallar: yatırım tavsiyesi YOK (al/sat/ne zaman/hedef fiyat), kişisel bilgi istenmez, kaba/spam yorumlara cevap yok.
Görev Zamanlayıcı'da 2 saatte bir (YTBot_YorumCevap). Yeni yorum yoksa Claude çağrılmaz (kota harcamaz).

Kullanım: .venv/Scripts/python.exe tools/comment_agent.py [--dry]   (--dry: göndermez, sadece önerileri yazar)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SP_UNATTENDED", "1")

from pipeline.stages.s09_upload import _get_credentials  # noqa: E402

BRAIN = ROOT / "output" / "_brain"
STATE = BRAIN / "comment_agent_state.json"
REVIEW = BRAIN / "comment_review.json"
WORK = ROOT / "output" / "_agents" / "comments"
MAX_PER_RUN = 25

PROMPT = """Sen "Finans Kanalı" YouTube kanalının yorum yöneticisisin (kanal: Türkçe kişisel finans/piyasa analizi; altın, dolar, borsa, Fed).
Aşağıdaki izleyici yorumlarına kanal adına kısa, sıcak, doğal Türkçe cevaplar yaz.

KURALLAR (kesin):
- YATIRIM TAVSİYESİ YOK: "al/sat/şimdi gir/bekle", hedef fiyat, "bence yükselir" gibi yönlendirme ASLA. Soru buna yönelikse:
  kararın kişiye ait olduğunu nazikçe söyle, videodaki verilere/seviyelere yönlendir.
- Uydurma rakam/olay yok. Emin olmadığın bilgi için "needs_review": true yap.
- 1-2 cümle, en fazla ~220 karakter. Emoji en fazla 1. Kanal adını tekrar etme. "ben <sunucu>" gibi kendini tanıtma yok.
- Konuşmayı sürdür: uygun yerde izleyiciye kısa bir karşı soru sor (yorum derinliği algoritmada önemli).
- Teşekkür/övgü yorumuna samimi kısa teşekkür + bir sonraki videoya davet.
- Eleştiriye savunmaya geçmeden, teşekkür edip düzeltme varsa kabul et; ciddi bir hata iddiasıysa needs_review: true.
- Kaba, spam, link, siyasi kavga, alakasız yorum -> reply: null (cevap verme).
- Hassas/kişisel durum (borç, iflas, sağlık) -> empatik, genel cevap + needs_review: true.

Yalnızca JSON döndür (başka metin yok):
[{"id": "<yorum id>", "reply": "<cevap ya da null>", "needs_review": true|false, "why": "<kısa gerekçe>"}]

YORUMLAR:
"""


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def fetch_new(yt, channel_id: str, seen: set[str]) -> list[dict]:
    out = []
    req = yt.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=channel_id, maxResults=50, order="time",
                                   textFormat="plainText")
    pages = 0
    while req is not None and pages < 3:
        res = req.execute()
        pages += 1
        for th in res.get("items", []):
            top = th["snippet"]["topLevelComment"]
            sn = top["snippet"]
            if top["id"] in seen or sn.get("authorChannelId", {}).get("value") == channel_id:
                continue
            # kanal zaten cevap verdiyse atla
            replies = th.get("replies", {}).get("comments", [])
            if any(r["snippet"].get("authorChannelId", {}).get("value") == channel_id for r in replies):
                continue
            out.append({"id": top["id"], "video_id": sn.get("videoId") or th["snippet"].get("videoId"), "author": sn.get("authorDisplayName"),
                        "text": sn.get("textOriginal", "")[:600], "at": sn.get("publishedAt")})
        req = yt.commentThreads().list_next(req, res)
    return out[:MAX_PER_RUN]


def moderate(yt, approve: list[str] | None, reject: list[str] | None) -> int:
    """Onay kuyruğu: --approve [id...] gönderir, --reject [id...] siler. Gönderilen/silinenler 'görüldü' sayılır."""
    review = load(REVIEW, [])
    state = load(STATE, {"seen": []})
    seen = set(state["seen"])
    sel = (lambda ids: (lambda x: not ids or x["id"] in ids))
    keep, sent, dropped = [], 0, 0
    for x in review:
        if approve is not None and sel(approve)(x):
            try:
                yt.comments().insert(part="snippet", body={"snippet": {"parentId": x["id"], "textOriginal": x["draft"][:500]}}).execute()
                sent += 1
                seen.add(x["id"])
                continue
            except Exception as e:  # noqa: BLE001
                print(f"gönderilemedi {x['id']}: {str(e)[:120]}")
        elif reject is not None and sel(reject)(x):
            dropped += 1
            seen.add(x["id"])
            continue
        keep.append(x)
    REVIEW.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    state["seen"] = sorted(seen)[-5000:]
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print(f"{sent} gönderildi, {dropped} silindi, kuyrukta {len(keep)} kaldı")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--approve", nargs="*", help="onay kuyruğundaki cevapları gönder (id verilmezse hepsi)")
    ap.add_argument("--reject", nargs="*", help="kuyruktan sil (id verilmezse hepsi)")
    a = ap.parse_args()
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=_get_credentials())
    if a.approve is not None or a.reject is not None:
        return moderate(yt, a.approve, a.reject)
    me = yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]
    state = load(STATE, {"seen": []})
    seen = set(state["seen"])
    new = fetch_new(yt, me, seen)
    if not new:
        print("yeni yorum yok")
        return 0
    titles = {}
    ids = sorted({c["video_id"] for c in new if c["video_id"]})
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute().get("items", []):
            titles[v["id"]] = v["snippet"]["title"]
    lines = [json.dumps({"id": c["id"], "video": titles.get(c["video_id"], ""), "yazan": c["author"], "yorum": c["text"]}, ensure_ascii=False) for c in new]
    WORK.mkdir(parents=True, exist_ok=True)
    from tools.daily_run import Log, claude
    out = claude(PROMPT + "\n".join(lines), WORK, Log(WORK / "agent.log"))
    txt = str(out.get("result", ""))
    try:
        plan = json.loads(txt[txt.index("["): txt.rindex("]") + 1])
    except Exception as e:  # noqa: BLE001
        print(f"Claude çıktısı okunamadı: {e}: {txt[:300]}")
        return 1
    by_id = {c["id"]: c for c in new}
    review = load(REVIEW, [])
    posted = skipped = queued = 0
    for p in plan:
        c = by_id.get(p.get("id"))
        if not c:
            continue
        seen.add(c["id"])
        reply = (p.get("reply") or "").strip()
        if not reply:
            skipped += 1
            continue
        if p.get("needs_review") or a.dry:
            review.append({**c, "video": titles.get(c["video_id"], ""), "draft": reply, "why": p.get("why"), "queued_at": datetime.now().isoformat(timespec="seconds")})
            queued += 1
            continue
        try:
            yt.comments().insert(part="snippet", body={"snippet": {"parentId": c["id"], "textOriginal": reply[:500]}}).execute()
            posted += 1
        except Exception as e:  # noqa: BLE001
            review.append({**c, "draft": reply, "why": f"gönderilemedi: {str(e)[:120]}", "queued_at": datetime.now().isoformat(timespec="seconds")})
            queued += 1
    state["seen"] = sorted(seen)[-5000:]
    BRAIN.mkdir(parents=True, exist_ok=True)
    if not a.dry:  # deneme koşusu yorumları "görüldü" saymaz
        STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    REVIEW.write_text(json.dumps(review[-300:], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(new)} yeni yorum: {posted} cevaplandı, {queued} onay kuyruğunda, {skipped} cevapsız (spam/alakasız)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""9 Eki: yayın öncesi atılamayan yorumları (gizli/zamanlanmış videoda yorumlar kapalı) video yayına girince atar.
Kuyruk: output/_brain/pending_comments.json (pipeline/stages/s09_upload.queue_comment yazar).
Görev Zamanlayıcı'da saatlik çalışır (YTBot_Yorum). 3 günden eski ya da silinmiş videolar kuyruktan düşer.

Kullanım: .venv/Scripts/python.exe tools/post_pending_comments.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SP_UNATTENDED", "1")  # token düşmüşse tarayıcı açmasın

from pipeline.stages.s09_upload import PENDING_COMMENTS, _get_credentials  # noqa: E402


def main() -> int:
    if not PENDING_COMMENTS.exists():
        return 0
    q = json.loads(PENDING_COMMENTS.read_text(encoding="utf-8"))
    if not q:
        return 0
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=_get_credentials())
    st = {v["id"]: v["status"] for v in yt.videos().list(part="status", id=",".join(x["video_id"] for x in q[:50])).execute().get("items", [])}
    keep = []
    for x in q:
        old = datetime.now() - datetime.fromisoformat(x["queued_at"]) > timedelta(days=3)
        s = st.get(x["video_id"])
        if s is None or old:
            print(f"düştü: {x['video_id']} ({'silinmiş' if s is None else 'süre doldu'})")
            continue
        if s.get("privacyStatus") != "public":
            keep.append(x)
            continue
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": x["video_id"], "topLevelComment": {
                "snippet": {"textOriginal": x["text"]}}}}).execute()
            print(f"yorum atıldı: {x['video_id']}")
        except Exception as e:  # noqa: BLE001
            print(f"atılamadı, tekrar denenecek: {x['video_id']}: {str(e)[:150]}")
            keep.append(x)
    PENDING_COMMENTS.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

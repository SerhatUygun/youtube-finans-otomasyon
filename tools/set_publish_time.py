"""10 Eki: yüklenmiş (private, zamanlanmış) uzun videonun yayın saatini değiştir.
Kullanım: .venv/Scripts/python.exe tools/set_publish_time.py output/daily-YYYYMMDD 17:30
upload_result.json'daki video_id için status.publishAt güncellenir (privacyStatus private kalır, yerel saat)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("SP_UNATTENDED", "1")


def main() -> int:
    job = Path(sys.argv[1])
    job = job if job.is_absolute() else ROOT / job
    hhmm = sys.argv[2]
    import youtube_mcp as Y
    from pipeline.stages import s09_upload

    up = json.loads((job / "upload_result.json").read_text(encoding="utf-8"))
    when = s09_upload.publish_time(hhmm)
    yt = Y.yt()
    cur = yt.videos().list(part="status", id=up["video_id"]).execute()["items"][0]["status"]
    cur["privacyStatus"], cur["publishAt"] = "private", s09_upload._rfc3339(when)
    yt.videos().update(part="status", body={"id": up["video_id"], "status": cur}).execute()
    up["publish_at"] = when.isoformat(timespec="minutes")
    (job / "upload_result.json").write_text(json.dumps(up, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{up['video_id']} -> yayın {when:%d.%m %H:%M}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

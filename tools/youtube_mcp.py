"""10 Eki: Finans Kanalı YouTube MCP sunucusu (stdio) — Claude Code oturumunda kanal verisine doğrudan erişim.
Kanalın mevcut OAuth jetonlarını kullanır (secrets/youtube_token.json, youtube_analytics_token.json); üçüncü tarafa veri gitmez.
Yazma işlemi yalnız yorum cevabı ve onay kuyruğu (video silme/düzenleme YOK).

Kayıt: proje kökündeki .mcp.json ("ytbot-youtube").
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("SP_UNATTENDED", "1")

from mcp.server.mcpserver import MCPServer  # noqa: E402

srv = MCPServer("ytbot-youtube", instructions="Finans Kanalı kanalının YouTube verisi: kanal özeti, son videolar, video analizi, yorumlar, yorum onay kuyruğu.")
_YT = _YA = None


def yt():
    global _YT
    if _YT is None:
        from googleapiclient.discovery import build
        from pipeline.stages.s09_upload import _get_credentials
        _YT = build("youtube", "v3", credentials=_get_credentials(), cache_discovery=False)
    return _YT


def ya():
    global _YA
    if _YA is None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        _YA = build("youtubeAnalytics", "v2", credentials=Credentials.from_authorized_user_file(str(ROOT / "secrets" / "youtube_analytics_token.json")),
                    cache_discovery=False)
    return _YA


@srv.tool(description="Kanal özeti: abone, toplam izlenme, video sayısı + son N günün izlenme/izlenme süresi/abone kazancı.")
def channel_summary(days: int = 28) -> dict:
    ch = yt().channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
    end, start = date.today(), date.today() - timedelta(days=days)
    r = ya().reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end),
                             metrics="views,estimatedMinutesWatched,averageViewPercentage,subscribersGained,subscribersLost").execute()
    row = (r.get("rows") or [[0, 0, 0, 0, 0]])[0]
    return {"kanal": ch["snippet"]["title"], "istatistik": ch["statistics"], f"son_{days}_gun": dict(zip(
        ["izlenme", "izlenme_dk", "ort_izlenme_yuzde", "abone_kazanc", "abone_kayip"], row))}


@srv.tool(description="Son yüklenen videolar (Shorts dahil): başlık, tarih, izlenme, beğeni, yorum.")
def recent_videos(limit: int = 15) -> list[dict]:
    up = yt().channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt().playlistItems().list(part="contentDetails", playlistId=up, maxResults=min(limit, 50)).execute()["items"]
    ids = [i["contentDetails"]["videoId"] for i in items]
    vs = yt().videos().list(part="snippet,statistics,status", id=",".join(ids)).execute()["items"]
    return [{"id": v["id"], "baslik": v["snippet"]["title"], "tarih": v["snippet"]["publishedAt"][:16], "durum": v["status"]["privacyStatus"],
             **{k: int(v["statistics"].get(k, 0)) for k in ("viewCount", "likeCount", "commentCount")}} for v in vs]


@srv.tool(description="Tek videonun analizi: izlenme, ort. izlenme yüzdesi, abone kazancı, trafik kaynakları (son N gün).")
def video_analytics(video_id: str, days: int = 28) -> dict:
    end, start = str(date.today()), str(date.today() - timedelta(days=days))
    base = dict(ids="channel==MINE", startDate=start, endDate=end, filters=f"video=={video_id}")
    m = ya().reports().query(metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments,shares", **base).execute()
    t = ya().reports().query(metrics="views", dimensions="insightTrafficSourceType", sort="-views", **base).execute()
    hdr = [h["name"] for h in m.get("columnHeaders", [])]
    return {"metrikler": dict(zip(hdr, (m.get("rows") or [[]])[0])), "trafik": {r[0]: r[1] for r in t.get("rows", [])}}


@srv.tool(description="Kanaldaki son yorumlar (en yeni önce); cevaplanmamış olanlar işaretli.")
def recent_comments(limit: int = 30) -> list[dict]:
    me = yt().channels().list(part="id", mine=True).execute()["items"][0]["id"]
    res = yt().commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=me, maxResults=min(limit, 100), order="time", textFormat="plainText").execute()
    out = []
    for th in res.get("items", []):
        s = th["snippet"]["topLevelComment"]["snippet"]
        replied = any(r["snippet"].get("authorChannelId", {}).get("value") == me for r in th.get("replies", {}).get("comments", []))
        out.append({"id": th["snippet"]["topLevelComment"]["id"], "video": s.get("videoId"), "yazan": s.get("authorDisplayName"),
                    "yorum": s.get("textOriginal", "")[:400], "tarih": s.get("publishedAt", "")[:16], "cevaplandi": replied})
    return out


@srv.tool(description="Bir yoruma kanal adına cevap yazar (comment id = recent_comments'teki id).")
def reply_comment(comment_id: str, text: str) -> dict:
    r = yt().comments().insert(part="snippet", body={"snippet": {"parentId": comment_id, "textOriginal": text[:500]}}).execute()
    return {"ok": True, "id": r["id"]}


@srv.tool(description="Yorum ajanının onay kuyruğu (tools/comment_agent.py): taslak cevaplar.")
def comment_review_queue() -> list[dict]:
    p = ROOT / "output" / "_brain" / "comment_review.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


@srv.tool(description="Günlük üretim durumu: bugünün log'unun son satırları ve son yüklenen uzun video.")
def daily_status(lines: int = 20) -> dict:
    logs = sorted((ROOT / "output" / "_daily").glob("20*.log"))
    tail = logs[-1].read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:] if logs else []
    from pipeline.daily.build import Build
    return {"log": logs[-1].name if logs else None, "son_satirlar": tail, "son_uzun_video": Build.latest_long()}


if __name__ == "__main__":
    srv.run("stdio")

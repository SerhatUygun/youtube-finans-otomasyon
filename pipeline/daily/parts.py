"""10 Eki: 40 dk'lık (mega) videoda segmentler tek JSON'a sığmaz; Claude `video_parts/part_NN.json` yazar
({"segments": [...], "scenes": [...]}, indeksler GLOBAL), bu modül bunları video.json'a birleştirir.
"""
from __future__ import annotations

import json
from pathlib import Path


def merge_parts(job_dir: Path) -> int:
    """video_parts/part_*.json -> video.json['segments'/'scenes'] (ada göre sıralı). Dönüş: birleşen parça sayısı."""
    parts = sorted((job_dir / "video_parts").glob("part_*.json"))
    vj = job_dir / "video.json"
    if not parts or not vj.exists():
        return 0
    video = json.loads(vj.read_text(encoding="utf-8"))
    segs, scenes = [], []
    for p in parts:
        d = json.loads(p.read_text(encoding="utf-8"))
        segs += d.get("segments", [])
        scenes += d.get("scenes", [])
    video["segments"], video["scenes"] = segs, scenes
    vj.write_text(json.dumps(video, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(parts)

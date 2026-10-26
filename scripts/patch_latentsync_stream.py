"""LatentSync restore_video: kareleri listede biriktirmek yerine akış halinde yazar (16GB RAM). İdempotent."""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
if "YOUTUBEBOT: akış" in s:
    print("stream patch: zaten uygulanmış")
    sys.exit(0)
rep = [
    ("            out_frames.append(out_frame)\n        return np.stack(out_frames, axis=0)",
     "            yield out_frame  # YOUTUBEBOT: akış halinde (1080p'de tüm kareleri RAM'de tutmak 16GB'ı tüketiyordu)"),
    ("        out_frames = []\n        print(f\"Restoring {len(faces)} faces...\")", "        print(f\"Restoring {len(faces)} faces...\")"),
    ("        synced_video_frames = self.restore_video(torch.cat(synced_video_frames), video_frames, boxes, affine_matrices)\n\n"
     "        audio_samples_remain_length = int(synced_video_frames.shape[0] / video_fps * audio_sample_rate)",
     "        synced_faces = torch.cat(synced_video_frames)\n        n_synced = len(synced_faces)\n"
     "        synced_video_frames = self.restore_video(synced_faces, video_frames, boxes, affine_matrices)\n\n"
     "        audio_samples_remain_length = int(n_synced / video_fps * audio_sample_rate)"),
]
for a, b in rep:
    if s.count(a) != 1:
        sys.exit(f"stream patch: beklenen kod bulunamadı: {a[:50]!r}")
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("stream patch: uygulandı")

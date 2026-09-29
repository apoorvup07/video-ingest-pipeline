"""Turn one source video into an adaptive-bitrate HLS package with FFmpeg."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rendition:
    name: str
    height: int
    video_kbps: int
    audio_kbps: int = 128

    @property
    def bandwidth(self) -> int:
        """Peak bandwidth in bits/s advertised in the master playlist (10% headroom)."""
        return int((self.video_kbps + self.audio_kbps) * 1000 * 1.1)


DEFAULT_LADDER: tuple[Rendition, ...] = (
    Rendition("360p", 360, 800),
    Rendition("720p", 720, 2800),
)


def build_ffmpeg_command(
    source: Path,
    out_dir: Path,
    rendition: Rendition,
    segment_seconds: int = 6,
) -> list[str]:
    """Build the FFmpeg command for one rendition.

    Keyframes are forced every `segment_seconds` so every rendition cuts at the
    same points; that alignment is what lets a player switch bitrates cleanly.
    """
    variant_dir = out_dir / rendition.name
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source),
        "-vf", f"scale=-2:{rendition.height}",
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main",
        "-pix_fmt", "yuv420p",  # 8-bit 4:2:0: what 'main' profile and every player expect
        "-b:v", f"{rendition.video_kbps}k",
        "-maxrate", f"{int(rendition.video_kbps * 1.07)}k",
        "-bufsize", f"{rendition.video_kbps * 2}k",
        "-force_key_frames", f"expr:gte(t,n_forced*{segment_seconds})",
        "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", f"{rendition.audio_kbps}k", "-ac", "2",
        "-f", "hls",
        "-hls_time", str(segment_seconds),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(variant_dir / "seg_%05d.ts"),
        str(variant_dir / "index.m3u8"),
    ]


def write_master_playlist(out_dir: Path, ladder: tuple[Rendition, ...]) -> Path:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for r in ladder:
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={r.bandwidth},NAME=\"{r.name}\"")
        lines.append(f"{r.name}/index.m3u8")
    master = out_dir / "master.m3u8"
    master.write_text("\n".join(lines) + "\n")
    return master


def segment(
    source: Path,
    out_dir: Path,
    ladder: tuple[Rendition, ...] = DEFAULT_LADDER,
    segment_seconds: int = 6,
) -> Path:
    """Encode `source` into HLS renditions under `out_dir`; return the master playlist."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH")
    if not source.is_file():
        raise FileNotFoundError(source)

    for r in ladder:
        (out_dir / r.name).mkdir(parents=True, exist_ok=True)
        cmd = build_ffmpeg_command(source, out_dir, r, segment_seconds)
        log.info("encoding %s -> %s", source.name, r.name)
        subprocess.run(cmd, check=True)
    return write_master_playlist(out_dir, ladder)

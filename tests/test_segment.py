import shutil
import subprocess
from pathlib import Path

import pytest

from ingest.segment import DEFAULT_LADDER, Rendition, build_ffmpeg_command, segment, write_master_playlist


def test_command_forces_aligned_keyframes(tmp_path):
    cmd = build_ffmpeg_command(Path("in.mp4"), tmp_path, Rendition("720p", 720, 2800), segment_seconds=4)
    assert "expr:gte(t,n_forced*4)" in cmd
    assert cmd[cmd.index("-hls_time") + 1] == "4"
    assert cmd[-1].endswith("720p/index.m3u8")


def test_master_playlist_lists_every_rendition(tmp_path):
    master = write_master_playlist(tmp_path, DEFAULT_LADDER).read_text()
    for r in DEFAULT_LADDER:
        assert f"{r.name}/index.m3u8" in master
        assert f"BANDWIDTH={r.bandwidth}" in master


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_segment_real_video(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=8:size=640x360:rate=25",
         "-f", "lavfi", "-i", "sine=duration=8", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)],
        check=True,
    )
    out = tmp_path / "hls"
    master = segment(src, out, segment_seconds=4)
    assert master.exists()
    for r in DEFAULT_LADDER:
        segments = list((out / r.name).glob("seg_*.ts"))
        assert len(segments) == 2  # 8 s of video / 4 s segments

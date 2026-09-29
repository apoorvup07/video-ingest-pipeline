"""Publish an HLS package to S3 with the headers CloudFront and players need."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".mp4": "video/mp4",
}

# Segments never change once written, so edges and browsers can keep them for a
# year. Playlists are small and are what you'd update to fix a package, so they
# get a short TTL.
SEGMENT_CACHE = "public, max-age=31536000, immutable"
PLAYLIST_CACHE = "public, max-age=60"

# Large files go up in 16 MiB parts, 4 at a time; a failed part is retried
# instead of restarting the whole file.
TRANSFER = TransferConfig(multipart_threshold=16 * 1024**2, multipart_chunksize=16 * 1024**2,
                          max_concurrency=4)
RETRIES = Config(retries={"max_attempts": 8, "mode": "adaptive"})


@dataclass
class UploadResult:
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def headers_for(path: Path) -> dict[str, str]:
    suffix = path.suffix.lower()
    content_type = CONTENT_TYPES.get(suffix, "application/octet-stream")
    cache = PLAYLIST_CACHE if suffix == ".m3u8" else SEGMENT_CACHE
    return {"ContentType": content_type, "CacheControl": cache}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _already_uploaded(s3, bucket: str, key: str, digest: str) -> bool:
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return head.get("Metadata", {}).get("sha256") == digest


def upload_package(package_dir: Path, bucket: str, prefix: str, s3=None) -> UploadResult:
    """Upload every file under `package_dir` to s3://bucket/prefix/.

    Re-running is safe: files whose SHA-256 matches the object already in S3 are
    skipped, so a crash halfway through can simply be retried. Playlists are
    uploaded last so a player never sees a playlist pointing at missing segments.
    """
    s3 = s3 or boto3.client("s3", config=RETRIES)
    files = sorted(p for p in package_dir.rglob("*") if p.is_file())
    files.sort(key=lambda p: p.suffix == ".m3u8")  # segments first, playlists last

    result = UploadResult()
    for path in files:
        key = f"{prefix.strip('/')}/{path.relative_to(package_dir).as_posix()}"
        digest = _sha256(path)
        if _already_uploaded(s3, bucket, key, digest):
            result.skipped.append(key)
            continue
        extra = {**headers_for(path), "Metadata": {"sha256": digest}}
        s3.upload_file(str(path), bucket, key, ExtraArgs=extra, Config=TRANSFER)
        result.uploaded.append(key)
        log.info("uploaded s3://%s/%s", bucket, key)
    return result

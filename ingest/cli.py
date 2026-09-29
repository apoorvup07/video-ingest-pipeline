"""Command line entry point: segment a video and publish it."""

from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path

from ingest.segment import segment
from ingest.upload import upload_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__)
    parser.add_argument("source", type=Path, help="source video file")
    parser.add_argument("--bucket", required=True, help="origin S3 bucket")
    parser.add_argument("--prefix", required=True, help="key prefix, e.g. titles/<title-id>")
    parser.add_argument("--segment-seconds", type=int, default=6)
    parser.add_argument("--cdn-domain", help="CloudFront domain, used to print the playback URL")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with tempfile.TemporaryDirectory() as tmp:
        segment(args.source, Path(tmp), segment_seconds=args.segment_seconds)
        result = upload_package(Path(tmp), args.bucket, args.prefix)

    print(f"uploaded {len(result.uploaded)} files, skipped {len(result.skipped)} unchanged")
    if args.cdn_domain:
        print(f"playback: https://{args.cdn_domain}/{args.prefix.strip('/')}/master.m3u8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

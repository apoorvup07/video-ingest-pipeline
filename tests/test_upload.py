import boto3
import pytest
from moto import mock_aws

from ingest.upload import PLAYLIST_CACHE, SEGMENT_CACHE, upload_package

BUCKET = "origin-bucket"


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-1")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})
        yield client


@pytest.fixture
def package(tmp_path):
    (tmp_path / "720p").mkdir()
    (tmp_path / "master.m3u8").write_text("#EXTM3U\n720p/index.m3u8\n")
    (tmp_path / "720p" / "index.m3u8").write_text("#EXTM3U\nseg_00000.ts\n")
    (tmp_path / "720p" / "seg_00000.ts").write_bytes(b"\x47" * 188 * 10)
    return tmp_path


def test_headers_per_file_type(s3, package):
    upload_package(package, BUCKET, "titles/demo", s3=s3)
    seg = s3.head_object(Bucket=BUCKET, Key="titles/demo/720p/seg_00000.ts")
    pl = s3.head_object(Bucket=BUCKET, Key="titles/demo/master.m3u8")
    assert seg["ContentType"] == "video/mp2t" and seg["CacheControl"] == SEGMENT_CACHE
    assert pl["ContentType"] == "application/vnd.apple.mpegurl" and pl["CacheControl"] == PLAYLIST_CACHE


def test_playlists_uploaded_after_segments(s3, package):
    result = upload_package(package, BUCKET, "titles/demo", s3=s3)
    first_playlist = next(i for i, k in enumerate(result.uploaded) if k.endswith(".m3u8"))
    assert all(not k.endswith(".m3u8") for k in result.uploaded[:first_playlist])
    assert result.uploaded[0].endswith(".ts")


def test_rerun_is_idempotent(s3, package):
    upload_package(package, BUCKET, "titles/demo", s3=s3)
    again = upload_package(package, BUCKET, "titles/demo", s3=s3)
    assert again.uploaded == [] and len(again.skipped) == 3
    (package / "master.m3u8").write_text("#EXTM3U\n# changed\n")
    third = upload_package(package, BUCKET, "titles/demo", s3=s3)
    assert third.uploaded == ["titles/demo/master.m3u8"]

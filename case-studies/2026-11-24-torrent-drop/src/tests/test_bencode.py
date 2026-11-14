import hashlib
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from bencode import TorrentMeta, TorrentParseError, parse_torrent_bytes


def test_parse_single_and_multi_file_torrent():
    info_single = b"d6:lengthi12345e4:name9:Movie.mkv12:piece lengthi16384e6:pieces20:12345678901234567890e"
    torrent_single = b"d8:announce18:http://tracker/ann4:info" + info_single + b"e"
    meta = parse_torrent_bytes(torrent_single)
    assert isinstance(meta, TorrentMeta)
    assert meta.info_hash == hashlib.sha1(info_single).hexdigest()
    assert meta.name == "Movie.mkv"
    assert meta.total_size == 12345

    info_multi = b"d5:filesld6:lengthi100e4:pathl7:cd1.mp3eed6:lengthi250e4:pathl7:cd2.mp3eee4:name5:Album12:piece lengthi16384e6:pieces20:12345678901234567890e"
    torrent_multi = b"d4:info" + info_multi + b"e"
    meta_m = parse_torrent_bytes(torrent_multi)
    assert isinstance(meta_m, TorrentMeta)
    assert meta_m.info_hash == hashlib.sha1(info_multi).hexdigest()
    assert meta_m.name == "Album"
    assert meta_m.total_size == 350


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"not-bencode",
        b"l4:teste",
        b"d8:announce4:teste",
        b"d4:infod6:lengthi10eee",
        b"d4:infoi42ee",
        b"d4:info4:teste",
        b"d4:infol4:teste",
        b"d4:infod4:name4:test5:filesleee",  # empty files list
        b"d4:infod4:name4:test5:filesld6:lengthi-5eeee",  # negative length in file
        b"d4:infod4:name4:test6:lengthi-10eee",  # negative single length
        b"d4:infod4:name4:test6:length10:not-an-inteee",  # non-int length
        b"d4:infod4:name4:test6:lengthi10e5:filesld6:lengthi10eeee",  # both length and files
        b"d4:infod4:name4:teste",  # neither length nor files
        b"d4:infod4:name0:6:lengthi10eee",  # empty name
        b"d4:infod4:namei123e6:lengthi10eee",  # non-string name
        b"d4:infod6:lengthi12345e4:name9:Movie.mkveextra",  # trailing data
    ],
)
def test_parse_invalid_torrent_raises(bad: bytes):
    with pytest.raises(TorrentParseError):
        parse_torrent_bytes(bad)


def test_parse_torrent_with_trailing_garbage():
    info_single = b"d6:lengthi12345e4:name9:Movie.mkv12:piece lengthi16384e6:pieces20:12345678901234567890e"
    torrent = b"d4:info" + info_single + b"etrailing"
    with pytest.raises(TorrentParseError):
        parse_torrent_bytes(torrent)


def test_parse_torrent_non_utf8_name():
    # Invalid UTF-8 sequence in name should fall back with replacement character
    info_raw = b"d6:lengthi10e4:name4:bad\xff12:piece lengthi16384e6:pieces20:12345678901234567890e"
    torrent = b"d4:info" + info_raw + b"e"
    meta = parse_torrent_bytes(torrent)
    assert meta.name == "bad\ufffd"
    assert meta.total_size == 10
    assert meta.info_hash == hashlib.sha1(info_raw).hexdigest()


def test_parse_torrent_missing_length_and_files():
    info_raw = b"d4:name5:Valid12:piece lengthi16384e6:pieces20:12345678901234567890e"
    torrent = b"d4:info" + info_raw + b"e"
    with pytest.raises(TorrentParseError):
        parse_torrent_bytes(torrent)


def test_non_bytes_input_raises():
    with pytest.raises(TorrentParseError):
        parse_torrent_bytes("string-not-bytes")  # type: ignore[arg-type]
    with pytest.raises(TorrentParseError):
        parse_torrent_bytes(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "corrupt_bencode",
    [
        b"i-0e",
        b"i05e",
        b"i-05e",
        b"ie",
        b"d",
        b"l",
        b"4:sp",  # too short
        b"04:spam",  # leading zero in length
        b"di123e4:teste",  # integer key in dict
    ],
)
def test_corrupt_bencode_values(corrupt_bencode: bytes):
    with pytest.raises(TorrentParseError):
        parse_torrent_bytes(corrupt_bencode)


def test_parse_magnet_hex_with_dn():
    from bencode import parse_magnet_uri

    h = "A1B2C3D4E5F60718293A4B5C6D7E8F9012345678"
    uri = f"magnet:?xt=urn:btih:{h}&dn=My%20Movie%20%282024%29&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337"
    meta = parse_magnet_uri(uri)
    assert meta.info_hash == h.lower()
    assert meta.name == "My Movie (2024)"
    assert meta.total_size == 0


def test_parse_magnet_base32_and_missing_dn():
    import base64
    from bencode import parse_magnet_uri

    raw_bytes = bytes(range(20))
    b32 = base64.b32encode(raw_bytes).decode("ascii").lower()
    meta = parse_magnet_uri(f"  MAGNET:?xt=urn:btih:{b32}&dn=   ")
    assert meta.info_hash == raw_bytes.hex()
    assert meta.name == f"magnet-{raw_bytes.hex()[:12]}"
    assert meta.total_size == 0


def test_parse_magnet_hybrid_v1_v2_uses_btih_and_truncates_dn():
    from bencode import parse_magnet_uri

    h = "0123456789abcdef0123456789abcdef01234567"
    v2 = "1220" + ("ab" * 32)
    long_name = "x" * 300
    uri = f"magnet:?xt=urn:btmh:{v2}&xt=urn:btih:{h}&dn={long_name}"
    meta = parse_magnet_uri(uri)
    assert meta.info_hash == h
    assert meta.name == "x" * 255


def test_parse_magnet_v2_only_rejected():
    from bencode import parse_magnet_uri

    v2 = "1220" + ("ab" * 32)
    with pytest.raises(TorrentParseError, match="btmh"):
        parse_magnet_uri(f"magnet:?xt=urn:btmh:{v2}&dn=Test")


@pytest.mark.parametrize(
    "bad_uri",
    [
        "",
        "   ",
        "http://example.com/?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
        "magnet:",
        "magnet:?",
        "magnet:?dn=OnlyName",
        "magnet:?xt=urn:btih:short",
        "magnet:?xt=urn:btih:" + ("z" * 40),
        "magnet:?xt=urn:btih:" + ("1" * 32),  # '1' is invalid base32
    ],
)
def test_parse_magnet_invalid_raises(bad_uri: str):
    from bencode import parse_magnet_uri

    with pytest.raises(TorrentParseError):
        parse_magnet_uri(bad_uri)


def test_parse_magnet_too_large_raises():
    from bencode import MAX_MAGNET_LENGTH, MagnetTooLargeError, parse_magnet_uri

    h = "0123456789abcdef0123456789abcdef01234567"
    oversized = f"magnet:?xt=urn:btih:{h}&dn=" + ("a" * (MAX_MAGNET_LENGTH + 10))
    with pytest.raises(MagnetTooLargeError):
        parse_magnet_uri(oversized)

from __future__ import annotations

import base64
import hashlib
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

MAX_MAGNET_LENGTH = 16384
_HEX_40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_B32_32_RE = re.compile(r"^[A-Za-z2-7]{32}$")


class TorrentParseError(ValueError):
    """Raised when parsing or validating .torrent bencode fails."""


class MagnetTooLargeError(TorrentParseError):
    """Raised when a magnet URI exceeds MAX_MAGNET_LENGTH."""


@dataclass
class TorrentMeta:
    info_hash: str
    name: str
    total_size: int


class _BencodeDecoder:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.len = len(data)
        self.info_span: tuple[int, int] | None = None

    def decode_value(self) -> Any:
        if self.pos >= self.len:
            raise TorrentParseError("Unexpected end of bencoded data")
        ch = self.data[self.pos : self.pos + 1]
        if ch == b"i":
            return self.decode_int()
        if ch == b"l":
            return self.decode_list()
        if ch == b"d":
            return self.decode_dict(is_root=False)
        if ch.isdigit():
            return self.decode_bytes()
        raise TorrentParseError(f"Unexpected token {ch!r} at byte {self.pos}")

    def decode_int(self) -> int:
        self.pos += 1  # skip 'i'
        end = self.data.find(b"e", self.pos)
        if end == -1:
            raise TorrentParseError("Unterminated integer")
        raw = self.data[self.pos : end]
        if not raw:
            raise TorrentParseError("Empty integer value")
        if raw == b"-0" or (raw.startswith(b"0") and len(raw) > 1) or (raw.startswith(b"-0")):
            raise TorrentParseError("Invalid integer encoding")
        try:
            val = int(raw)
        except ValueError as exc:
            raise TorrentParseError(f"Malformed integer: {raw!r}") from exc
        self.pos = end + 1
        return val

    def decode_bytes(self) -> bytes:
        colon = self.data.find(b":", self.pos)
        if colon == -1:
            raise TorrentParseError("Unterminated byte string length")
        raw_len = self.data[self.pos : colon]
        if not raw_len.isdigit():
            raise TorrentParseError(f"Invalid byte string length: {raw_len!r}")
        if len(raw_len) > 1 and raw_len.startswith(b"0"):
            raise TorrentParseError("Leading zero in string length")
        length = int(raw_len)
        start = colon + 1
        end = start + length
        if end > self.len:
            raise TorrentParseError("Byte string extends beyond data length")
        self.pos = end
        return self.data[start:end]

    def decode_list(self) -> list[Any]:
        self.pos += 1  # skip 'l'
        items: list[Any] = []
        while self.pos < self.len and self.data[self.pos : self.pos + 1] != b"e":
            items.append(self.decode_value())
        if self.pos >= self.len or self.data[self.pos : self.pos + 1] != b"e":
            raise TorrentParseError("Unterminated list")
        self.pos += 1  # skip 'e'
        return items

    def decode_dict(self, is_root: bool = False) -> dict[bytes, Any]:
        self.pos += 1  # skip 'd'
        items: dict[bytes, Any] = {}
        while self.pos < self.len and self.data[self.pos : self.pos + 1] != b"e":
            if not self.data[self.pos : self.pos + 1].isdigit():
                raise TorrentParseError(f"Dictionary key must be string at byte {self.pos}")
            key = self.decode_bytes()
            val_start = self.pos
            val = self.decode_value()
            val_end = self.pos
            if is_root and key == b"info":
                self.info_span = (val_start, val_end)
            items[key] = val
        if self.pos >= self.len or self.data[self.pos : self.pos + 1] != b"e":
            raise TorrentParseError("Unterminated dictionary")
        self.pos += 1  # skip 'e'
        return items


def parse_torrent_bytes(data: bytes) -> TorrentMeta:
    """Parse raw .torrent bytes and extract info_hash, name, and total_size."""
    if not isinstance(data, (bytes, bytearray)):
        raise TorrentParseError("Expected bytes or bytearray")
    if not data:
        raise TorrentParseError("Empty torrent data")
    if data[0:1] != b"d":
        raise TorrentParseError("Torrent data must start with a bencoded dictionary")

    decoder = _BencodeDecoder(bytes(data))
    root = decoder.decode_dict(is_root=True)
    if decoder.pos != decoder.len:
        raise TorrentParseError("Trailing bytes after root bencode dictionary")

    info = root.get(b"info")
    if not isinstance(info, dict) or decoder.info_span is None:
        raise TorrentParseError("Torrent missing or invalid 'info' dictionary")

    raw_name = info.get(b"name")
    if not isinstance(raw_name, (bytes, bytearray)) or not raw_name:
        raise TorrentParseError("Torrent info missing or empty 'name'")
    name = bytes(raw_name).decode("utf-8", errors="replace")

    has_length = b"length" in info
    has_files = b"files" in info

    if has_length and not has_files:
        length = info[b"length"]
        if not isinstance(length, int) or isinstance(length, bool) or length < 0:
            raise TorrentParseError("Invalid 'length' in torrent info")
        total_size = length
    elif has_files and not has_length:
        files = info[b"files"]
        if not isinstance(files, list) or not files:
            raise TorrentParseError("Invalid or empty 'files' in torrent info")
        total_size = 0
        for f in files:
            if not isinstance(f, dict) or b"length" not in f:
                raise TorrentParseError("File entry in 'files' must be a dict with 'length'")
            flen = f[b"length"]
            if not isinstance(flen, int) or isinstance(flen, bool) or flen < 0:
                raise TorrentParseError("Invalid file length in 'files'")
            total_size += flen
    else:
        raise TorrentParseError("Torrent info must contain either 'length' or 'files', not both or neither")

    start, end = decoder.info_span
    info_bytes = data[start:end]
    info_hash = hashlib.sha1(info_bytes).hexdigest()

    return TorrentMeta(info_hash=info_hash, name=name, total_size=total_size)


def parse_magnet_uri(uri: str) -> TorrentMeta:
    """Parse and validate a magnet:? URI, normalizing btih to 40-char lowercase hex."""
    if not isinstance(uri, str):
        raise TorrentParseError("Magnet link must be a string")
    cleaned = uri.strip()
    if not cleaned:
        raise TorrentParseError("Empty magnet link")
    if len(cleaned) > MAX_MAGNET_LENGTH:
        raise MagnetTooLargeError(
            f"Magnet link exceeds maximum length ({len(cleaned)} > {MAX_MAGNET_LENGTH} chars)"
        )

    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme.lower() != "magnet" or not parsed.query:
        raise TorrentParseError("Invalid magnet URI format (expected magnet:?...)")

    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    xt_values = params.get("xt", [])

    info_hash: str | None = None
    saw_btmh = False
    for xt in xt_values:
        xt_clean = xt.strip()
        lower_xt = xt_clean.lower()
        if lower_xt.startswith("urn:btih:"):
            token = xt_clean[9:]
            if _HEX_40_RE.match(token):
                info_hash = token.lower()
                break
            if _B32_32_RE.match(token):
                try:
                    raw = base64.b32decode(token.upper(), casefold=False)
                except Exception as exc:
                    raise TorrentParseError(f"Invalid Base32 btih hash: {exc}") from exc
                if len(raw) == 20:
                    info_hash = raw.hex().lower()
                    break
        elif lower_xt.startswith("urn:btmh:"):
            saw_btmh = True

    if not info_hash:
        if saw_btmh:
            raise TorrentParseError(
                "BitTorrent v2-only magnet links (urn:btmh) without a v1 btih hash are not supported"
            )
        raise TorrentParseError("Magnet link is missing a valid urn:btih info hash")

    dn_values = params.get("dn", [])
    display_name = ""
    for dn in dn_values:
        cand = dn.strip()
        if cand:
            display_name = cand[:255]
            break
    if not display_name:
        display_name = f"magnet-{info_hash[:12]}"

    return TorrentMeta(info_hash=info_hash, name=display_name, total_size=0)

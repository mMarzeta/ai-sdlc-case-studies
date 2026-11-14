from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
import httpx


class QBittorrentError(RuntimeError):
    """Raised when a qBittorrent Web API operation fails."""
    pass


@dataclass
class TorrentProgress:
    info_hash: str
    state: str
    progress: float
    dlspeed: int
    eta: int
    content_path: str
    size: int
    name: str = ""


class QBittorrentClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._logged_in = False

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> QBittorrentClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    async def _login(self) -> None:
        url = f"{self.base_url}/api/v2/auth/login"
        try:
            res = await self._client.post(
                url,
                data={"username": self.username, "password": self.password},
            )
        except httpx.HTTPError as exc:
            raise QBittorrentError(f"Login network error: {exc}") from exc

        if res.status_code not in (200, 204) or res.text.strip() == "Fails.":
            self._logged_in = False
            raise QBittorrentError(f"Login failed ({res.status_code}): {res.text.strip()}")

        self._logged_in = True

    def _has_session_cookie(self) -> bool:
        return any(k == "SID" or k.startswith("QBT_SID_") for k in self._client.cookies.keys())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: Any = None,
        params: Any = None,
        files: Any = None,
        allow_409: bool = False,
    ) -> httpx.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"

        # Ensure logged in if missing cookie / not yet authenticated
        if not self._logged_in or not self._has_session_cookie():
            await self._login()

        try:
            res = await self._client.request(
                method,
                url,
                data=data,
                params=params,
                files=files,
            )
        except httpx.HTTPError as exc:
            raise QBittorrentError(f"Request {method} {path} error: {exc}") from exc

        # Automatic single retry on 401/403 (expired session)
        if res.status_code in (401, 403):
            await self._login()
            try:
                res = await self._client.request(
                    method,
                    url,
                    data=data,
                    params=params,
                    files=files,
                )
            except httpx.HTTPError as exc:
                raise QBittorrentError(f"Retry request {method} {path} error: {exc}") from exc

        if allow_409 and res.status_code == 409:
            return res

        if res.status_code >= 400:
            raise QBittorrentError(f"qBittorrent error {res.status_code} on {method} {path}: {res.text.strip()}")

        return res

    async def ensure_configured(self, downloads_dir: str, network_interface: str) -> None:
        dl_dir = str(downloads_dir).rstrip("/")
        prefs = {
            "save_path": f"{dl_dir}/complete",
            "temp_path_enabled": True,
            "temp_path": f"{dl_dir}/incomplete",
            "max_ratio_enabled": True,
            "max_ratio": 0.0,
            "max_ratio_act": 0,
            "current_network_interface": network_interface,
        }
        await self._request(
            "POST",
            "/api/v2/app/setPreferences",
            data={"json": json.dumps(prefs)},
        )
        for cat in ("movies", "music"):
            await self._request(
                "POST",
                "/api/v2/torrents/createCategory",
                data={
                    "category": cat,
                    "savePath": f"{dl_dir}/complete/{cat}",
                },
                allow_409=True,
            )

    async def add_torrent(self, torrent_bytes: bytes, filename: str, category: str) -> None:
        files = {
            "torrents": (filename, torrent_bytes, "application/x-bittorrent"),
        }
        data = {
            "category": category,
            "ratioLimit": "0.0",
        }
        res = await self._request(
            "POST",
            "/api/v2/torrents/add",
            data=data,
            files=files,
        )
        if res.text.strip() == "Fails.":
            raise QBittorrentError("Failed to add torrent: qBittorrent returned 'Fails.'")

    async def add_magnet(self, magnet_uri: str, category: str) -> None:
        data = {
            "urls": magnet_uri,
            "category": category,
            "ratioLimit": "0.0",
        }
        res = await self._request(
            "POST",
            "/api/v2/torrents/add",
            data=data,
        )
        if res.text.strip() == "Fails.":
            raise QBittorrentError("Failed to add magnet: qBittorrent returned 'Fails.'")

    async def get_torrents(self, hashes: list[str]) -> dict[str, TorrentProgress]:
        if not hashes:
            return {}
        hashes_param = "|".join(hashes)
        res = await self._request(
            "GET",
            "/api/v2/torrents/info",
            params={"hashes": hashes_param},
        )
        try:
            items = res.json()
        except Exception as exc:
            raise QBittorrentError(f"Failed to parse torrents JSON: {exc}") from exc

        if not isinstance(items, list):
            raise QBittorrentError(f"Expected list from /api/v2/torrents/info, got {type(items).__name__}")

        result: dict[str, TorrentProgress] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            h = str(item.get("hash", ""))
            raw_size = item.get("size", item.get("total_size", 0))
            prog = TorrentProgress(
                info_hash=h,
                state=str(item.get("state", "")),
                progress=float(item.get("progress", 0.0)),
                dlspeed=int(item.get("dlspeed", 0)),
                eta=int(item.get("eta", 0)),
                content_path=str(item.get("content_path", "")),
                size=max(0, int(raw_size or 0)),
                name=str(item.get("name") or ""),
            )
            result[h] = prog
            result[h.lower()] = prog
        return result

    async def delete_torrent(self, info_hash: str, delete_files: bool = False) -> None:
        data = {
            "hashes": info_hash,
            "deleteFiles": "true" if delete_files else "false",
        }
        await self._request(
            "POST",
            "/api/v2/torrents/delete",
            data=data,
        )

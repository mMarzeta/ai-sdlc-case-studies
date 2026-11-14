from __future__ import annotations

import asyncio
import dataclasses
import inspect
import ipaddress
import logging
import socket
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bencode import (
    MAX_MAGNET_LENGTH,
    MagnetTooLargeError,
    TorrentMeta,
    TorrentParseError,
    parse_magnet_uri,
    parse_torrent_bytes,
)
from config import Settings, load_settings
from db import ACTIVE_STATES, DuplicateActiveJobError, JobRecord, JobStore
from torrent_client import QBittorrentClient, QBittorrentError
from vpn_status import VpnStatus, get_vpn_status
from worker import run_worker_loop

logger = logging.getLogger(__name__)


class MagnetRequest(BaseModel):
    magnet: str
    category: str


def _normalize_category(category: str) -> str:
    cat = category.strip().lower()
    if cat not in ("movies", "music"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Must be 'movies' or 'music'.",
        )
    return cat

STANDARD_ALLOWED_NETS: list[ipaddress._BaseNetwork] = [
    # IPv4 loopback & RFC1918 private & link-local & Tailscale CGNAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.2.10/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # Tailscale CGNAT
    # IPv6 loopback & link-local & ULA & Tailscale IPv6
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),  # Covers fd00::/8 ULA
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),  # Tailscale IPv6
]


def discover_host_ipv6_subnets() -> list[ipaddress._BaseNetwork]:
    """Discover active non-loopback global IPv6 /64 subnets on the host via `ip -6 -o addr`."""
    subnets: list[ipaddress._BaseNetwork] = []
    try:
        proc = subprocess.run(
            ["ip", "-6", "-o", "addr", "show", "scope", "global"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if proc.returncode != 0:
            return subnets

        for line in proc.stdout.splitlines():
            tokens = line.strip().split()
            if not tokens or len(tokens) < 4:
                continue
            iface = tokens[1]
            if any(iface.startswith(prefix) for prefix in ("tailscale", "wg", "tun", "docker", "br-")):
                continue
            if "inet6" in tokens:
                idx = tokens.index("inet6")
                if idx + 1 < len(tokens):
                    cidr = tokens[idx + 1]
                    addr_str = cidr.split("/")[0]
                    try:
                        addr = ipaddress.ip_address(addr_str)
                    except ValueError:
                        continue
                    # Ignore ULA or non-global
                    if (
                        isinstance(addr, ipaddress.IPv6Address)
                        and addr.is_global
                        and addr not in ipaddress.ip_network("fc00::/7")
                    ):
                        net = ipaddress.IPv6Network(f"{addr}/64", strict=False)
                        if net not in subnets:
                            subnets.append(net)
    except Exception as exc:
        logger.debug("IPv6 subnet discovery skipped or failed: %s", exc)

    return subnets


def is_allowed_ip(
    ip_str: str,
    extra_nets: list[ipaddress._BaseNetwork] | None = None,
) -> bool:
    """Check if the provided IP string belongs to local LAN, Tailscale, or allowed subnets."""
    try:
        clean = ip_str.split("%")[0].strip("[]")
        addr = ipaddress.ip_address(clean)
    except (ValueError, AttributeError):
        return False

    # Unwrap IPv4-mapped IPv6 (e.g., ::ffff:192.0.2.10)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped

    nets = STANDARD_ALLOWED_NETS + (list(extra_nets) if extra_nets else [])
    for net in nets:
        if addr.version == net.version and addr in net:
            return True

    return False


def create_app(
    cfg: Settings | None = None,
    store: JobStore | None = None,
    qb: QBittorrentClient | None = None,
    vpn_checker: Callable[[], Any] | None = None,
    start_worker: bool = True,
) -> FastAPI:
    if cfg is None:
        cfg = load_settings()
    if store is None:
        store = JobStore(cfg.db_path)
    if qb is None:
        qb = QBittorrentClient(cfg.qb_url, cfg.qb_user, cfg.qb_password)

    allowed_nets: list[ipaddress._BaseNetwork] = []
    for s in cfg.allowed_subnets:
        try:
            allowed_nets.append(ipaddress.ip_network(s.strip(), strict=False))
        except ValueError:
            logger.warning("Invalid allowed subnet configured: %s", s)

    for net in discover_host_ipv6_subnets():
        if net not in allowed_nets:
            allowed_nets.append(net)

    http_client: httpx.AsyncClient | None = None

    async def check_vpn() -> VpnStatus:
        if vpn_checker is not None:
            res = vpn_checker()
            if inspect.isawaitable(res):
                return await res
            return res

        nonlocal http_client
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=3.0)
        return await get_vpn_status(cfg.gluetun_url, http_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        store.init_schema()

        # Best-effort initial qBittorrent configuration
        try:
            await qb.ensure_configured("/downloads", cfg.qb_interface)
            app.state.qb_configured = True
        except Exception as exc:
            app.state.qb_configured = False
            logger.warning("Could not pre-configure qBittorrent on startup: %s", exc)

        worker_task: asyncio.Task | None = None
        stop_event = asyncio.Event()
        if start_worker:
            worker_task = asyncio.create_task(
                run_worker_loop(store, qb, cfg, stop_event, interval_sec=3.0)
            )

        try:
            yield
        finally:
            # Shutdown
            if worker_task is not None:
                stop_event.set()
                try:
                    await asyncio.wait_for(worker_task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    worker_task.cancel()

            try:
                await qb.aclose()
            except Exception:
                pass

            nonlocal http_client
            if http_client is not None:
                await http_client.aclose()

    app = FastAPI(
        title="torrent-drop",
        description="Wi-Fi / Tailscale torrent drop service behind Proton VPN",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.cfg = cfg
    app.state.store = store
    app.state.qb = qb
    app.state.vpn_checker = check_vpn
    app.state.allowed_subnets = allowed_nets
    app.state.qb_configured = False

    @app.middleware("http")
    async def ip_allowlist_middleware(request: Request, call_next):
        client = request.client
        if not client or not client.host or not is_allowed_ip(client.host, app.state.allowed_subnets):
            client_ip = client.host if client else "unknown"
            return JSONResponse(
                status_code=403,
                content={"detail": f"Forbidden: IP {client_ip} not allowed"},
            )
        return await call_next(request)

    static_dir = Path(__file__).resolve().parent / "static"
    index_file = static_dir / "index.html"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=FileResponse)
    async def serve_index():
        if index_file.is_file():
            return FileResponse(index_file, media_type="text/html")
        return HTMLResponse("<h1>Torrent Drop</h1>", status_code=200)

    @app.get("/api/status")
    async def get_status():
        vpn = await app.state.vpn_checker()
        vpn_dict = {
            "connected": vpn.connected,
            "status_text": vpn.status_text,
            "public_ip": vpn.public_ip,
            "country": vpn.country,
        }
        jobs = [dataclasses.asdict(j) for j in store.list_jobs(limit=50)]
        return {"vpn": vpn_dict, "jobs": jobs}

    async def _enqueue_job(
        meta: TorrentMeta,
        cat: str,
        submit_fn: Callable[[], Awaitable[None]],
    ) -> JobRecord:
        vpn = await app.state.vpn_checker()
        if not vpn.connected:
            raise HTTPException(
                status_code=503,
                detail=f"VPN is not connected ({vpn.status_text}). Downloads blocked.",
            )

        # Retry qBittorrent configuration if not yet configured
        if not getattr(app.state, "qb_configured", False):
            try:
                await qb.ensure_configured("/downloads", cfg.qb_interface)
                app.state.qb_configured = True
            except Exception as exc:
                logger.warning("qBittorrent is unreachable during submission: %s", exc)
                raise HTTPException(
                    status_code=503,
                    detail=f"qBittorrent client is unreachable or not ready: {exc}",
                )

        try:
            job = store.create_job(
                info_hash=meta.info_hash,
                name=meta.name,
                category=cat,
                total_size=meta.total_size,
            )
        except DuplicateActiveJobError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        try:
            await submit_fn()
        except Exception as exc:
            store.update_job(job.id, state="failed", error=f"qBittorrent submission error: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to submit torrent to client: {exc}")

        return job

    @app.post("/api/torrents", status_code=201)
    async def upload_torrent(
        file: UploadFile = File(...),
        category: str = Form(...),
    ):
        cat = _normalize_category(category)

        content = await file.read()
        max_size = 10 * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Payload too large ({len(content)} bytes). Maximum size is {max_size} bytes.",
            )
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty torrent file.")

        try:
            meta = parse_torrent_bytes(content)
        except TorrentParseError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid .torrent file: {exc}",
            )

        filename = file.filename or f"{meta.name}.torrent"
        job = await _enqueue_job(meta, cat, lambda: qb.add_torrent(content, filename, cat))
        return dataclasses.asdict(job)

    @app.post("/api/magnets", status_code=201)
    async def submit_magnet(payload: MagnetRequest):
        cat = _normalize_category(payload.category)
        magnet_uri = payload.magnet.strip()
        if len(magnet_uri) > MAX_MAGNET_LENGTH:
            raise HTTPException(
                status_code=413,
                detail=f"Magnet URI too large ({len(magnet_uri)} chars). Maximum length is {MAX_MAGNET_LENGTH}.",
            )

        try:
            meta = parse_magnet_uri(magnet_uri)
        except MagnetTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc))
        except TorrentParseError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid magnet link: {exc}")

        job = await _enqueue_job(meta, cat, lambda: qb.add_magnet(magnet_uri, cat))
        return dataclasses.asdict(job)

    @app.delete("/api/torrents/{job_id}")
    async def delete_job_endpoint(job_id: int):
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        if job.state in {"moving", "post_processing"}:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete job {job_id} while in state '{job.state}' (active post-processing).",
            )

        if job.state in ACTIVE_STATES:
            try:
                await qb.delete_torrent(job.info_hash, delete_files=True)
            except Exception as exc:
                logger.warning("Failed to delete torrent %s from client: %s", job.info_hash, exc)

        store.delete_job(job_id)
        return {"ok": True, "id": job_id}

    return app


def create_dual_stack_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))
    sock.listen(2048)
    return sock


if __name__ == "__main__":
    import uvicorn

    settings = load_settings()
    sock = create_dual_stack_socket(settings.app_port)
    config = uvicorn.Config(create_app(cfg=settings), log_level="info")
    uvicorn.Server(config).run(sockets=[sock])

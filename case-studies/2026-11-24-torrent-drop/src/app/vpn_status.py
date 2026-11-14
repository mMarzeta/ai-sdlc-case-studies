from __future__ import annotations

from dataclasses import dataclass
import httpx


@dataclass
class VpnStatus:
    connected: bool
    status_text: str
    public_ip: str | None = None
    country: str | None = None


async def get_vpn_status(gluetun_url: str, client: httpx.AsyncClient) -> VpnStatus:
    base = gluetun_url.rstrip("/")
    timeout = 2.0
    try:
        status_res = await client.get(f"{base}/v1/vpn/status", timeout=timeout)
        if status_res.status_code == 404:
            status_res = await client.get(f"{base}/v1/openvpn/status", timeout=timeout)
        status_res.raise_for_status()
        status_data = status_res.json()
        status_text = status_data.get("status", "unknown") if isinstance(status_data, dict) else "unknown"

        if status_text != "running":
            return VpnStatus(
                connected=False,
                status_text=status_text,
                public_ip=None,
                country=None,
            )

        ip_res = await client.get(f"{base}/v1/publicip/ip", timeout=timeout)
        ip_res.raise_for_status()
        ip_data = ip_res.json()
        public_ip = ip_data.get("public_ip") if isinstance(ip_data, dict) else None
        country = ip_data.get("country") if isinstance(ip_data, dict) else None

        return VpnStatus(
            connected=True,
            status_text=status_text,
            public_ip=public_ip,
            country=country,
        )
    except Exception as exc:
        return VpnStatus(
            connected=False,
            status_text=f"error: {exc}",
            public_ip=None,
            country=None,
        )

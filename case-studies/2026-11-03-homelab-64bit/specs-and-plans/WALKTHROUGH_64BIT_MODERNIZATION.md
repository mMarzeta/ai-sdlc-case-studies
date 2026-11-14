# Walkthrough: 64-Bit Docker Compose Modernization & Hardening

## Overview
Completed the 64-bit modernization and security hardening across all Docker Compose stacks on Raspberry Pi 5 (`aarch64`, Debian 13 Trixie, Docker 29.7.2).

---

## Changes Made

### 1. Main Stack (`~/projects/docker-compose.yml`)
- **Security**: Removed `security_opt: [seccomp=unconfined]` from `umami`, `ghost-db`, and `gitea` to re-enable default Linux kernel syscall sandboxing.
- **Platform Cleanup**: Removed redundant `platform: linux/arm64/v8` and `platform: linux/arm64` overrides across `homeassistant`, `umami`, `ghost-db`, and `gitea`.
- **Database Healthcheck**: Added `mysqladmin ping` healthcheck to `ghost-db` with 10s interval/start_period.
- **Service Dependencies**: Updated `ghost` `depends_on` to require `ghost-db` `condition: service_healthy`.
- **Grafana Plugins**: Removed deprecated AngularJS `grafana-simple-json-datasource` plugin from `GF_INSTALL_PLUGINS`.
- **Least Privilege**: Removed unnecessary `SYS_TIME` capability from `pihole`.
- **Umami Healthcheck**: Added `start_period: 30s` to prevent transient unhealthy state during Next.js database check and cold boot.

### 2. Jellyfin Stack (`~/projects/jellyfin/docker-compose.yml`)
- Removed `platform: linux/arm64/v8` and `security_opt: [seccomp=unconfined]`.

### 3. Immich Stack (`~/projects/immich-app/docker-compose.yml`)
- Removed `platform: linux/arm64/v8` and `security_opt: [seccomp=unconfined]` across `immich-server`, `immich-machine-learning`, `redis` (Valkey), and `database` (PostgreSQL 14 vectorchord).

### 4. GoOffline Stack (`~/projects/gooffline/backend/docker-compose.yml`)
- Removed `platform: linux/arm64/v8` and `security_opt: [seccomp=unconfined]` from `cdify-api`.

---

## Validation & Results

### Container Status & Health Check
All 17 containers across all stacks are running and healthy:

| Container | Image / Stack | Health Status |
| :--- | :--- | :--- |
| `projects-umami-1` | Umami (Postgres) | **Healthy** |
| `immich_server` | Immich Server v2.2.3 | **Healthy** |
| `immich_postgres` | Postgres 14 Vectorchord | **Healthy** |
| `immich_machine_learning` | Immich ML v2.2.3 | **Healthy** |
| `immich_redis` | Valkey 8 | **Healthy** |
| `jellyfin` | Jellyfin Media Server | **Healthy** |
| `projects-ghost-db-1` | MySQL 8/9 | **Healthy** (new) |
| `ghost` | Ghost 6 | **Running** (waiting on healthy DB) |
| `gitea` | Gitea 1.26.1 | **Running** |
| `grafana` | Grafana 12.3.1 | **Running** |
| `prometheus` | Prometheus 3.11.3 | **Running** |
| `pihole` | Pi-hole v6 | **Healthy** |
| `uptime-kuma` | Uptime Kuma | **Healthy** |
| `homeassistant` | Home Assistant | **Running** |
| `projects-navidrome-1` | Navidrome 0.59.0 | **Running** |
| `projects-db-1` | Postgres 16 | **Healthy** |
| `pokemon-monitor` | Pokemon Monitor | **Running** |

### Endpoint Smoke Tests
```text
✅ Grafana         -> HTTP 200 (http://localhost:3000/api/health)
✅ Umami           -> HTTP 200 (http://localhost:3001/api/heartbeat)
✅ Gitea           -> HTTP 200 (http://localhost:3002/)
✅ Uptime Kuma     -> HTTP 200 (http://localhost:3003/)
✅ Prometheus      -> HTTP 200 (http://localhost:9090/-/healthy)
✅ Ghost           -> HTTP 301 (http://localhost:2368/ -> HTTPS redirect)
✅ Jellyfin        -> HTTP 200 (http://localhost:8096/health)
✅ Navidrome       -> HTTP 200 (http://localhost:4533/ping)
✅ Immich Server   -> HTTP 200 (http://localhost:2283/api/server/ping)
```

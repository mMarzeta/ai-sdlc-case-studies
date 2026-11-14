# Raspberry Pi 5 Homelab Modernization & Enhancement Report

## 1. Media Copy Verification (SSD to Raspberry Pi)
- **Status**: **100% Completed & Verified**.
- **Source**: `/mnt/ssd/pi_migration_backup/media_backup` (External SSD, exFAT, 312 GB total)
- **Destination Verification**:
  - **Jellyfin Media**: `202 GB` (216,068,428,710 bytes) — **0 missing files**.
  - **Navidrome Music**: `103 GB` (110,095,324,327 bytes) — **0 missing files**.
  - **Immich Library**: `5.3 GB` (5,677,426,096 bytes) — **0 missing files** (synced missing `.immich` markers).
  - **Movies**: **0 missing files**.
- **Result**: All media has been copied to your NVMe drive.

---

## 2. Implemented System Enhancements

### Step 1: PCIe Gen 3 Mode Enabled
- **What was done**: Added `dtparam=pciex1_gen=3` under `[pi5]` in `/boot/firmware/config.txt`.
- **Effect**: Upgrades NVMe transfer speed from PCIe Gen 2 (~450 MB/s) to PCIe Gen 3 (~850–900 MB/s) on next reboot.

### Step 2: EEPROM Bootloader Firmware Update Staged
- **What was done**: Executed `sudo rpi-eeprom-update -a` to stage the May 2026 bootloader firmware in `/boot/firmware`.
- **Effect**: Flashes new power management, PCIe stability, and fan curve improvements automatically on next reboot.

### Step 3: Global Docker Log Rotation Configured
- **What was done**: Created `/etc/docker/daemon.json` with 20MB / 3-file rotation policy and reloaded Docker (`sudo systemctl reload docker`).
- **Effect**: Protects NVMe disk space by preventing unbounded container log file growth.

### Step 4: Hardware & Container Metrics in Prometheus / Grafana
- **What was done**:
  - Added `cadvisor` container in `Projects/docker-compose.yml` on the `monitoring` network.
  - Linked native host `prometheus-node-exporter` (port 9100) and `cadvisor` (port 8080) in `~/projects/prometheus/prometheus.yml`.
- **Effect**: Live hardware stats (thermals, NVMe I/O, RAM, ZRAM) and per-container CPU/RAM stats are now active in Prometheus & Grafana.

### Step 5: Automated Nightly Database Backups
- **What was done**:
  - Created `~/projects/backup_databases.sh` with safe transactional dumps (`pg_dumpall`, `mysqldump --single-transaction --quick --no-tablespaces`) and gzip compression.
  - Backs up:
    1. PostgreSQL 16 (`projects-db-1`: Umami & Gitea)
    2. MySQL 8/9 (`projects-ghost-db-1`: Ghost)
    3. Immich PostgreSQL (`immich_postgres`)
  - Configured user cron job to run nightly at **03:30 AM** with automatic 7-day backup pruning.
  - Test run executed successfully in `~/backups/databases/`.

### Step 6: Automatic OS Security Updates (`unattended-upgrades`)
- **What was done**: Installed and configured `unattended-upgrades` with periodic daily security checks (`/etc/apt/apt.conf.d/20auto-upgrades`).
- **Effect**: Automatically patches Debian security CVEs without unwanted reboots (`Automatic-Reboot "false"`).

---

## 3. Overall Service & Health Status

| Container / Service | Status | Port / Ingress |
| :--- | :--- | :--- |
| `cadvisor` | **Healthy** | 8080 (Prometheus scrape) |
| `projects-umami-1` | **Healthy** | 3001 |
| `immich_server` | **Healthy** | 2283 |
| `immich_postgres` | **Healthy** | 5432 |
| `immich_machine_learning` | **Healthy** | Internal |
| `immich_redis` | **Healthy** | 6379 |
| `jellyfin` | **Healthy** | 8096, 7359/udp |
| `ghost` | **Running** | 2368 (blog.marzeta.pl) |
| `projects-ghost-db-1` | **Healthy** | 3306 |
| `gitea` | **Running** | 3002, 222 (git) |
| `grafana` | **Running** | 3000 (grafana.marzeta.pl) |
| `prometheus` | **Running** | 9090 |
| `pihole` | **Healthy** | Host network (DNS) |
| `uptime-kuma` | **Healthy** | 3003 |
| `homeassistant` | **Running** | Host network |
| `projects-navidrome-1` | **Running** | 4533 |
| `projects-db-1` | **Healthy** | 5432 |
| `pokemon-monitor` | **Running** | Background bot |
| `cloudflared` | **Active (Running)** | Ingress Tunnel |

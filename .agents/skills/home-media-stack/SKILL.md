---
name: home-media-stack
description: >-
  Manage, configure, monitor, and troubleshoot the home media infrastructure:
  Jellyfin media server, Jellite, Nginx caching reverse proxy, DLNA/UPnP streamers
  (WiiM, Yamaha MusicCast), SSDP advertiser, automated cache pre-warming,
  M3U case-sensitivity repair, and Proxmox/Unraid storage.
---

# Home Media Stack (Jellyfin, Nginx Cache, DLNA & Warmup)

Expert guide and operational cheatsheet for the home streaming architecture hosted on Proxmox/Unraid (`192.168.2.251`).

---

## ⚡ Quick Reference Commands

| Action | Command |
| :--- | :--- |
| **Check All Services** | `ssh root@jellyfin "systemctl status nginx jellyfin jellyfin-cache-prewarm.timer jellyfin-proxy-ssdp --no-pager"` |
| **Inspect Cache Hits/Misses** | `ssh root@jellyfin "tail -n 30 /var/log/nginx/cache.log"` |
| **Filter Non-Hit Requests** | `ssh root@jellyfin "grep -E 'cache=(MISS\|STALE\|EXPIRED)' /var/log/nginx/cache.log \| tail -n 25"` |
| **Run Cache Pre-warmer** | `ssh root@jellyfin "systemctl start jellyfin-cache-prewarm.service && journalctl -u jellyfin-cache-prewarm -f"` |
| **Fix Playlist M3U Casing** | `ssh root@jellyfin "python3 /usr/local/bin/fix-m3u-case.py /mnt/user/music/LOSSLESS/playlists /var/lib/jellyfin/data/jellyfin.db"` |
| **Check SSDP Discovery** | `ssh root@jellyfin "systemctl status jellyfin-proxy-ssdp.service"` |
| **Purge Cache & Reload** | `ssh root@jellyfin "rm -rf /var/cache/nginx/jellyfin/* && systemctl reload nginx"` |
| **Push Git Updates** | `cd /Users/zenedith/git/jellyfin-cache-proxy && git push origin main && git push unraid main` |

---

## 🏗️ Architecture Summary

- **Host (`192.168.2.251`)**: Proxmox container/VM hosting Jellyfin & Nginx.
- **Frontend Reverse Proxy**: Nginx listening on ports `:80` and `:8096`. Caches DLNA SOAP `POST` requests and Jellyfin REST API queries in `/var/cache/nginx/jellyfin`.
- **Backend Origin**: Jellyfin Media Server bound internally to port `:8095`.
- **Storage**: Fast NVMe mounted at `/mnt/user/music/LOSSLESS` (exFAT).
- **UPnP Discovery**: `jellyfin-proxy-ssdp.py` multicasts on UDP `1900` advertising `jellyfin-proxy` on port `8096` to prevent WiiM and Yamaha MusicCast from bypassing the cache proxy.
- **Clients**:
  - **WiiM Ultra / WiiM Pro** (`192.168.2.221`, `192.168.2.14`): UPnP / DLNA Browse & Stream.
  - **Yamaha MusicCast**: Network audio streamer discovering via SSDP.
  - **LG TV / Web** (`192.168.2.150`, `192.168.2.11`): Jellyfin Web UI.
  - **Feishin Desktop** (`192.168.2.206`): Uses chunked queries (`Limit=200&StartIndex=0`).
  - **Finamp Mobile**: Uses standard user items endpoints.

Detailed architecture and network diagram: [architecture.md](./references/architecture.md)

---

## 🔧 Workflows & Procedures

### 1. Handling Slow Large Playlists (Deezer 6.7k, Sejsmograf 6.1k)
- Large playlists are cached under key `PL|$pl_id|$arg_UserId|$arg_Limit|$arg_StartIndex`.
- `jellyfin-cache-prewarm.py` pre-warms full lists, first chunk (`0..200`), and second chunk (`200..400`).
- If an end user sees a delay, verify if `jellyfin-cache-prewarm.service` has completed its run.
- Nginx `proxy_cache_use_stale updating` delivers existing cache in `<10ms` while updating in the background.

Detailed caching mechanics and directives: [nginx-cache.md](./references/nginx-cache.md)

### 2. Fixing Missing Songs in Playlists
- **Symptom**: Songs show on disk but disappear in Jellyfin playlists; `[WRN] Unable to find linked item at path` in logs.
- **Cause**: Case sensitivity mismatch between exFAT/Samba filesystem and Jellyfin's SQLite `BaseItems` table.
- **Solution**:
  ```bash
  ssh root@jellyfin "python3 /usr/local/bin/fix-m3u-case.py /mnt/user/music/LOSSLESS/playlists /var/lib/jellyfin/data/jellyfin.db"
  ```

Detailed maintenance procedures: [warmup-and-maintenance.md](./references/warmup-and-maintenance.md)

### 3. Diagnosing Network Streamers (WiiM / MusicCast)
- If the device can't discover the server: verify `jellyfin-proxy-ssdp.service`.
- If songs fail to play or cover art is missing: verify `sub_filter` in Nginx config to ensure `127.0.0.1` loopback URLs are replaced with `192.168.2.251:8096`.

Step-by-step diagnostic workflows: [troubleshooting.md](./references/troubleshooting.md)

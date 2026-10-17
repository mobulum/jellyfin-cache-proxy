# Troubleshooting & Diagnostics Runbook

## 1. Quick Health Check (One-Liner)

Check all core services at once:
```bash
ssh root@jellyfin "systemctl status nginx jellyfin jellyfin-cache-prewarm.timer jellyfin-proxy-ssdp.service --no-pager"
```

---

## 2. Inspecting Real-Time Nginx Cache Behavior

Follow the live cache log:
```bash
ssh root@jellyfin "tail -f /var/log/nginx/cache.log"
```

Filter for cache misses, stale updates, or errors:
```bash
ssh root@jellyfin "grep -E 'cache=(MISS|BYPASS|EXPIRED|STALE)' /var/log/nginx/cache.log | tail -n 30"
```

Understanding cache status tags:
- `HIT`: Served directly from disk in `<10ms`.
- `STALE`: Client served instantly with existing cache (`~0.2s`), while Nginx re-fetches fresh data from upstream `:8095` in the background.
- `MISS`: Not in cache; requested synchronously from Jellyfin origin `:8095`.
- `BYPASS`: Cache bypassed by headers (rare).

---

## 3. Investigating High Response Times (`rt=300s` or `rt=600s`)

If you see entries with `rt=300.000` or `rt=600.000` in `/var/log/nginx/cache.log`:
1. Check the client IP:
   - If `client=127.0.0.1`: This is **Nginx's background update subrequest** (`proxy_cache_background_update on`). The actual end user was served instantly with the stale copy and did not wait!
   - If the origin request exceeded `proxy_read_timeout` (600s), Jellyfin's SQLite database may have been locked by a library scan or heavy bulk query.
2. Check Jellyfin's CPU and disk load:
   ```bash
   ssh root@jellyfin "top -b -n 1 | head -n 20"
   ```
3. Check Nginx error logs:
   ```bash
   ssh root@jellyfin "tail -n 30 /var/log/nginx/error.log"
   ```

---

## 4. Missing Songs in Playlists / "Unable to find linked item at path"

If songs show up on the filesystem but do not appear in a playlist in Jellyfin / WiiM / Feishin:
1. Inspect Jellyfin warnings:
   ```bash
   ssh root@jellyfin "grep -i 'Unable to find linked item' /var/log/jellyfin/jellyfin*.log | tail -n 20"
   ```
2. Run the case-sensitivity fixer on the playlists folder:
   ```bash
   ssh root@jellyfin "python3 /usr/local/bin/fix-m3u-case.py /mnt/user/music/LOSSLESS/playlists /var/lib/jellyfin/data/jellyfin.db"
   ```
3. After fixing, Jellyfin automatically re-indexes the modified M3U files, restoring the missing tracks.

---

## 5. DLNA Device (WiiM / MusicCast) Can't Find Server

1. Verify SSDP advertiser is active:
   ```bash
   ssh root@jellyfin "systemctl status jellyfin-proxy-ssdp.service"
   ```
2. Verify port 8096 proxy responds to device description:
   ```bash
   curl -I http://192.168.2.251:8096/jellyfin-proxy/description.xml
   ```
3. Restart SSDP advertiser if necessary:
   ```bash
   ssh root@jellyfin "systemctl restart jellyfin-proxy-ssdp.service"
   ```

---

## 6. How to Completely Purge & Re-Warm Cache

If playlist data or library metadata changed significantly and you want a completely fresh cache:
```bash
# 1. Clear disk cache & reload Nginx
ssh root@jellyfin "rm -rf /var/cache/nginx/jellyfin/* && systemctl reload nginx"

# 2. Trigger pre-warming service
ssh root@jellyfin "systemctl start jellyfin-cache-prewarm.service"

# 3. Monitor progress
ssh root@jellyfin "journalctl -u jellyfin-cache-prewarm.service -f"
```

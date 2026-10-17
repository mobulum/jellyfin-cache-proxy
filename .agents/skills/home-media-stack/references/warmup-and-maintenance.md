# Warmup & Maintenance Tools

## 1. Automated Pre-warming Suite (`jellyfin-cache-prewarm.py`)

- **Script Path**: `/usr/local/bin/jellyfin-cache-prewarm.py`
- **Systemd Service**: `jellyfin-cache-prewarm.service`
- **Systemd Timer**: `jellyfin-cache-prewarm.timer` (runs every 4 hours + immediately after boot)

### How It Works
1. **Concurrency Protection**: Uses `/var/lock/jellyfin-cache-prewarm.lock` (`flock`) to prevent overlapping executions.
2. **DLNA Warmup**:
   - Queries Root container (`0..500`), Music root (`0..500`), Playlists container (`0..100`).
   - Discovers all DLNA playlists and queries chunks `0..10`, `0..100`, and `0..500` via SOAP POST.
3. **REST API Warmup**:
   - Fetches users list from `/Users`.
   - For each user:
     - Warms the user's **Playlists Folder View** (used when entering the playlists view on LG TV / Web).
     - Loops over playlists with $\ge 50$ tracks.
     - Warms **Feishin full items** (`/playlists/{id}/items?...`).
     - Warms **Feishin chunk 1** (`StartIndex=0&Limit=200`) -> renders initial view in 6ms!
     - Warms **Feishin chunk 2** (`StartIndex=200&Limit=200` if $>200$ tracks) -> ensures seamless scrolling!
     - Warms **Feishin metadata** (`/users/{uid}/items/{id}`).
     - Warms **Finamp items** (`/Items?ParentId=...`).
     - Warms **Jellyfin Web items** (`/Users/{uid}/Items?ParentId=...&Limit=300`).

### Managing the Service
```bash
# Check timer schedule
ssh root@jellyfin "systemctl list-timers | grep jellyfin"

# Manually trigger a cache warm-up
ssh root@jellyfin "systemctl start jellyfin-cache-prewarm.service"

# View warm-up execution logs
ssh root@jellyfin "journalctl -u jellyfin-cache-prewarm.service -n 50 --no-pager"
```

---

## 2. Playlist Case-Sensitivity Fixer (`fix-m3u-case.py`)

- **Script Path**: `/usr/local/bin/fix-m3u-case.py` (Source in repo: `tools/fix-m3u-case.py`)
- **Database**: `/var/lib/jellyfin/data/jellyfin.db`
- **Playlists**: `/mnt/user/music/LOSSLESS/playlists/`

### The Problem
Jellyfin queries track paths in SQLite (`BaseItems`) with **case-sensitive exact string comparison**. Because the music storage is on exFAT/Samba mounts, file paths match case-insensitively on disk, but Jellyfin logs:
```text
[WRN] Unable to find linked item at path "/mnt/user/music/LOSSLESS/Artist/..."
```
and silently drops the songs from the playlist in all players.

### Running the Fix
```bash
# Batch-fix all playlists in directory (recommended)
ssh root@jellyfin "python3 /usr/local/bin/fix-m3u-case.py /mnt/user/music/LOSSLESS/playlists /var/lib/jellyfin/data/jellyfin.db"

# Or fix a single playlist:
ssh root@jellyfin "python3 /usr/local/bin/fix-m3u-case.py /mnt/user/music/LOSSLESS/playlists/deezer.m3u /var/lib/jellyfin/data/jellyfin.db"
```
The script:
1. Connects to `jellyfin.db` in read-only mode (`mode=ro`).
2. Loads all indexed audio paths into a lowercase lookup map.
3. Rewrites the M3U using the exact canonical casing stored in Jellyfin's database.
4. Creates a backup with `.casefix_bak`.

---

## 3. Standalone SSDP Advertiser (`jellyfin-proxy-ssdp.py`)

- **Script Path**: `/usr/local/bin/jellyfin-proxy-ssdp.py`
- **Systemd Service**: `jellyfin-proxy-ssdp.service`
- **Port**: UDP 1900 (Multicast `239.255.255.250:1900`)

### Purpose
Advertises a secondary UPnP MediaServer device name (`jellyfin-proxy`) on port 8096 with its own unique USN/UUID. This allows UPnP control points (WiiM, Yamaha MusicCast) to see and select the cached proxy instance directly.

```bash
# Check SSDP status
ssh root@jellyfin "systemctl status jellyfin-proxy-ssdp.service"
```

---

## 4. Git Repository Maintenance

- **Local Repo**: `/Users/zenedith/git/jellyfin-cache-proxy`
- **GitHub Origin**: `git@github.com:mobulum/jellyfin-cache-proxy.git`
- **Unraid Mirror**: `ssh://git@192.168.2.8:2222/zenedith/jellyfin-cache-proxy.git`

```bash
# Push to both remotes
git push origin main
git push unraid main
```

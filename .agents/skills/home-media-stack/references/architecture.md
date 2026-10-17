# Home Media Stack Architecture & Infrastructure

## 1. Network Topology & Device Inventory

| Device / Role | Hostname / IP | Protocol / Ports | Purpose |
| :--- | :--- | :--- | :--- |
| **Jellyfin Host** | `jellyfin`<br>`192.168.2.251` | SSH (22)<br>HTTP (80, 8096)<br>Backend (8095)<br>SSDP (1900 UDP) | Proxmox LXC/VM running Jellyfin, Nginx cache proxy, and warmup services. |
| **Unraid Server** | `192.168.2.8` | SSH/Git (2222) | Local Git mirror (`ssh://git@192.168.2.8:2222/zenedith/jellyfin-cache-proxy.git`). |
| **Music Storage** | `/mnt/user/music` on `192.168.2.251` | exFAT (nvme2n1p2) | High-speed NVMe storage mounted with `uid=jellyfin,gid=jellyfin`. |
| **WiiM Streamers** | `192.168.2.221`<br>`192.168.2.14` | UPnP / DLNA Browse & Stream | Hi-Fi audio streamers (WiiM Ultra, WiiM Pro). |
| **Smart TV / Web** | `192.168.2.150`<br>`192.168.2.11` | HTTP (8096) | LG TV Jellyfin client and Web app. |
| **Feishin (Desktop)** | `192.168.2.206` | HTTP (8096) REST | Desktop client using paginated queries (`Limit=200&StartIndex=0`). |
| **Yamaha MusicCast**| LAN Broadcast | UPnP / DLNA (SSDP :1900) | Multi-room network audio receiver. |

---

## 2. Port Architecture on Jellyfin Host (`192.168.2.251`)

```mermaid
flowchart TD
    subgraph Clients["Clients"]
        WiiM["WiiM Streamers (UPnP/DLNA)"]
        TV["LG TV & Web Client"]
        Desktop["Feishin Desktop (REST)"]
        Mobile["Finamp Mobile (REST)"]
        MusicCast["Yamaha MusicCast (UPnP)"]
    end

    subgraph Host["Jellyfin Host (192.168.2.251)"]
        SSDP["SSDP Advertiser (:1900 UDP)\nService: jellyfin-proxy-ssdp"]
        Nginx["Nginx Reverse Proxy (:80, :8096)\nConfig: /etc/nginx/sites-available/jellyfin-cache.conf"]
        Cache[("/var/cache/nginx/jellyfin\n10 GB fast disk cache")]
        Jellyfin["Jellyfin Origin (:8095)\nService: jellyfin.service"]
        Storage[("/mnt/user/music/LOSSLESS\nPlaylists: /mnt/user/music/LOSSLESS/playlists")]
    end

    WiiM -->|Browse & Stream| Nginx
    TV -->|UI & Streams| Nginx
    Desktop -->|Paginated REST| Nginx
    Mobile -->|Audio Items REST| Nginx
    MusicCast -.->|Discover :8096| SSDP
    SSDP -.->|Advertises jellyfin-proxy| Clients
    Nginx <-->|Cache Check / Store| Cache
    Nginx -->|Proxy Pass (MISS / STALE)| Jellyfin
    Jellyfin <-->|Indexed Tracks & M3U| Storage
```

- **Port 8096 / 80**: Nginx frontend reverse proxy (where all clients and streamers connect).
- **Port 8095**: Jellyfin backend origin (internal, bound to localhost/127.0.0.1).
- **Port 1900 (UDP)**: SSDP multicast responder/advertiser for UPnP discovery.

---

## 3. Storage Hierarchy

- **Root Mount**: `/mnt/user/music` (exFAT filesystem, device `/dev/nvme2n1p2`).
- **Lossless Audio**: `/mnt/user/music/LOSSLESS/Artist/<ArtistName>/<AlbumName>/<TrackName>.<ext>`.
- **M3U Playlists**: `/mnt/user/music/LOSSLESS/playlists/`
  - `deezer.m3u` (~6,750 tracks)
  - `Sejsmograf.m3u` (~6,170 tracks)
  - `Jan.m3u` (240 tracks)
  - `Leon.m3u` (226 tracks)
  - `Zlot Famicon.m3u` (151 tracks)
  - `Splasher.m3u` (16 tracks)
- **Database**: `/var/lib/jellyfin/data/jellyfin.db` (SQLite).

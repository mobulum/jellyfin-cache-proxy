# Nginx Caching Proxy Configuration & Behavior

## 1. File Locations on Jellyfin Host (`192.168.2.251`)

- **Configuration**: `/etc/nginx/sites-available/jellyfin-cache.conf` (symlinked in `/etc/nginx/sites-enabled/`)
- **Cache Storage**: `/var/cache/nginx/jellyfin`
- **Cache Hit/Miss Log**: `/var/log/nginx/cache.log`
- **Error Log**: `/var/log/nginx/error.log`

---

## 2. Endpoints & Cache Keys

| Endpoint | Pattern | Cache Key | Typical Client |
| :--- | :--- | :--- | :--- |
| **Endpoint 1** | `/playlists/(?<pl_id>[^/]+)/items$` | `PL\|$pl_id\|$arg_UserId\|$arg_Limit\|$arg_StartIndex` | Feishin, Jellyfin Web |
| **Endpoint 2** | `/users/(?<u_uid>[^/]+)/items/(?<u_item_id>[^/]+)$` | `UITEM\|$u_uid\|$u_item_id` | Feishin Playlist Meta |
| **Endpoint 3** | `/items$` | `IT\|$arg_ParentId\|$arg_UserId\|$arg_Limit\|$arg_StartIndex\|$arg_SortBy\|$arg_SortOrder` | Finamp |
| **Endpoint 4** | `/users/(?<ui_uid>[^/]+)/items$` | `UITEMS\|$ui_uid\|$arg_ParentId\|$arg_Recursive\|$arg_IncludeItemTypes\|$arg_SortBy\|$arg_SortOrder\|$arg_StartIndex\|$arg_Limit` | Smart TV, Web, Folder Lists |
| **Endpoint 5** | `/artists`, `/artists/albumartists`, `/musicgenres` | `META\|$uri\|$args` | Metadata browsing |
| **Endpoint 6** | `/dlna/(.+)/contentdirectory/control$` | `SOAP\|$uri\|$http_soapaction\|$request_body` | WiiM, MusicCast (POST SOAP) |
| **Endpoint 7** | `/jellyfin-proxy/description.xml` | Standard static / proxy pass | UPnP Device Description |

---

## 3. Critical Nginx Directives & Why They Exist

```nginx
proxy_cache_use_stale updating error timeout http_500 http_502 http_503 http_504;
proxy_cache_background_update on;
proxy_cache_lock on;
proxy_cache_lock_timeout 300s;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
proxy_ignore_client_abort on;
```

1. **`proxy_cache_use_stale updating` + `proxy_cache_background_update on`**:
   - When a cached item expires, **the client never waits**! Nginx instantly serves the expired (stale) cache in `<10ms` (HTTP 200).
   - In the background, Nginx asynchronously opens a subrequest to `:8095` to re-fetch and store fresh data for next time.
2. **`proxy_read_timeout 600s`**:
   - For massive playlists (6,700+ songs like *deezer* or *Sejsmograf*), Jellyfin origin can take several minutes to serialize items from SQLite when busy. The 600s timeout prevents `upstream timed out (110: Connection timed out)` errors in Nginx's background update worker.
3. **`proxy_cache_lock on` + `proxy_cache_lock_timeout 300s`**:
   - If 5 clients request the same uncached large playlist at once, only ONE request goes to Jellyfin origin. The other 4 wait for the cache to populate, avoiding CPU/DB stampedes.
4. **`proxy_ignore_client_abort on`**:
   - If a client disconnects or aborts before Jellyfin finishes computing, Nginx still finishes the download and caches the result.
5. **CORS Headers Override**:
   - Nginx strips origin CORS headers (`proxy_hide_header Access-Control-Allow-Origin`) and injects uniform headers to ensure cached responses never break browser cross-origin checks in Feishin or Web clients.
6. **DLNA `sub_filter` URL Rewriting**:
   - Rewrites `http://127.0.0.1/` and `http://192.168.2.251/` to `http://192.168.2.251:8096/` in XML responses so streamers don't attempt loopback connections.

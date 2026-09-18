#!/usr/bin/env python3
"""
Jellyfin Cache Pre-warm Script
Iterates through DLNA root, playlist folders, and REST API playlists to warm up
the Nginx proxy cache. Ensures snappy response times (<10ms instead of 30-180s)
for massive music libraries.
"""

import urllib.request
import urllib.parse
import json
import re
import html
import time
import sys
import os
import fcntl

# === CONFIGURATION ===
# Nginx caching proxy URL (default: http://127.0.0.1:8096 or your server LAN IP)
CACHE_BASE = os.environ.get("JELLYFIN_CACHE_URL", "http://127.0.0.1:8096")

# Jellyfin backend origin URL (direct port, default: http://127.0.0.1:8095)
ORIGIN_BASE = os.environ.get("JELLYFIN_ORIGIN_URL", "http://127.0.0.1:8095")

# Jellyfin API Token (Generate in Dashboard -> Administration -> API Keys)
API_TOKEN = os.environ.get("JELLYFIN_API_TOKEN", "a886de1ed45e483c86baf352686091be")
AUTH_HEADER = f'MediaBrowser Token="{API_TOKEN}"'

# Lock file to avoid overlapping runs
LOCK_FILE_PATH = "/var/lock/jellyfin-cache-prewarm.lock"

# UPnP ContentDirectory Control Endpoint
DLNA_CONTROL_URL = f"{CACHE_BASE}/dlna/a69460b5-5dc7-4a6c-8a64-56a32efb9bad/contentdirectory/control"
DLNA_SOAP_ACTION = '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"'

FEISHIN_FIELDS = "Fields=Genres&Fields=DateCreated&Fields=MediaSources&Fields=ChildCount&Fields=ParentId&Fields=SortName"


def http_get(url, headers=None, timeout=180):
    req_headers = headers or {}
    req = urllib.request.Request(url, headers=req_headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            cache_status = resp.headers.get("X-Cache-Status", "-")
            elapsed = time.time() - t0
            return resp.status, cache_status, elapsed, data
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        return e.code, "ERROR", elapsed, b""
    except Exception as e:
        elapsed = time.time() - t0
        return 0, str(e), elapsed, b""


def dlna_browse(object_id, starting_index=0, requested_count=500, user_agent="okhttp/4.9.1"):
    soap_body = (
        f'<?xml version="1.0" encoding="utf-8" standalone="yes"?>'
        f'<s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" '
        f'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<s:Body>'
        f'<u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">'
        f'<ObjectID>{object_id}</ObjectID>'
        f'<BrowseFlag>BrowseDirectChildren</BrowseFlag>'
        f'<Filter>*</Filter>'
        f'<StartingIndex>{starting_index}</StartingIndex>'
        f'<RequestedCount>{requested_count}</RequestedCount>'
        f'<SortCriteria></SortCriteria>'
        f'</u:Browse>'
        f'</s:Body>'
        f'</s:Envelope>'
    )
    req = urllib.request.Request(
        DLNA_CONTROL_URL,
        data=soap_body.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": DLNA_SOAP_ACTION,
            "User-Agent": user_agent,
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read().decode("utf-8", errors="ignore")
            cache_status = resp.headers.get("X-Cache-Status", "NONE")
            elapsed = time.time() - t0
            return cache_status, elapsed, data
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [DLNA ERROR] ObjectID={object_id} count={requested_count}: {e}", file=sys.stderr)
        return "ERROR", elapsed, None


def prewarm_dlna():
    print("=== [1/2] Starting DLNA Pre-warming (WiiM / UPnP Players) ===")

    # 1. Root container
    st, el, _ = dlna_browse("0", 0, 500)
    print(f"  [{st}] DLNA Root (0..500) in {el:.2f}s")

    # 2. Playlists container (standard Jellyfin DLNA playlists folder ID)
    playlists_container_id = "97c5e2d06e8ef4ccf29609bd379498d4"
    st, el, xml_data = dlna_browse(playlists_container_id, 0, 100)
    print(f"  [{st}] DLNA Playlists Folder in {el:.2f}s")

    if xml_data:
        playlist_matches = re.findall(
            r'&lt;container.*?id="([a-f0-9]{32})".*?&lt;dc:title&gt;(.*?)&lt;/dc:title&gt;',
            xml_data,
        )
        print(f"  Found {len(playlist_matches)} DLNA playlists.")
        for pid, title in playlist_matches:
            title = html.unescape(title)
            # For massive playlists, pre-warm multiple chunk sizes (e.g. 10, 100, 500)
            # which match standard pagination patterns of UPnP control points
            for cnt in (10, 100, 500):
                st_pl, el_pl, _ = dlna_browse(pid, 0, cnt)
                print(f"  [{st_pl}] DLNA Playlist: '{title}' (0..{cnt}) in {el_pl:.2f}s")

    # 3. Music root folder
    music_root_id = "f137a2dd21bbc1b99aa5c0f6bf02a805"
    st, el, _ = dlna_browse(music_root_id, 0, 500)
    print(f"  [{st}] DLNA Music Root in {el:.2f}s")


def prewarm_rest():
    print("=== [2/2] Starting REST API Pre-warming (Feishin / Finamp) ===")

    users_url = f"{ORIGIN_BASE}/Users"
    code, _, el, data = http_get(users_url, headers={"Authorization": AUTH_HEADER}, timeout=30)
    if code != 200:
        print(f"  [ERROR] Failed to fetch users list (HTTP {code})", file=sys.stderr)
        return

    try:
        users = json.loads(data.decode("utf-8"))
    except Exception as e:
        print(f"  [ERROR] Failed to parse users JSON: {e}", file=sys.stderr)
        return

    for u in users:
        uid = u.get("Id")
        uname = u.get("Name")
        print(f"  Checking playlists for user: {uname} ({uid})...")

        pl_url = (
            f"{ORIGIN_BASE}/Items?IncludeItemTypes=Playlist&Recursive=true&UserId={uid}&Fields=ChildCount"
        )
        p_code, _, _, p_data = http_get(pl_url, headers={"Authorization": AUTH_HEADER}, timeout=30)
        if p_code != 200:
            continue

        try:
            pl_items = json.loads(p_data.decode("utf-8")).get("Items", [])
        except Exception:
            continue

        for item in pl_items:
            pid = item.get("Id")
            pname = item.get("Name")
            child_count = item.get("ChildCount") or 0

            # Only prewarm playlists that contain enough tracks to warrant caching
            if child_count < 50:
                continue

            print(f"    Warming REST playlist: '{pname}' ({child_count} tracks)...")

            # 1) Feishin items endpoint
            url_1 = f"{CACHE_BASE}/playlists/{pid}/items?{FEISHIN_FIELDS}&IncludeItemTypes=Audio&UserId={uid}"
            c1, st1, t1, _ = http_get(url_1, headers={"Authorization": AUTH_HEADER, "X-Warmup": "1"})
            print(f"      [Feishin items: {st1}] HTTP {c1} in {t1:.2f}s")

            # 2) Feishin metadata endpoint
            url_2 = f"{CACHE_BASE}/users/{uid}/items/{pid}?{FEISHIN_FIELDS}&Ids={pid}"
            c2, st2, t2, _ = http_get(url_2, headers={"Authorization": AUTH_HEADER, "X-Warmup": "1"})
            print(f"      [Feishin meta: {st2}] HTTP {c2} in {t2:.2f}s")

            # 3) Finamp items endpoint
            url_3 = f"{CACHE_BASE}/Items?UserId={uid}&IncludeItemTypes=Audio&ParentId={pid}"
            c3, st3, t3, _ = http_get(url_3, headers={"Authorization": AUTH_HEADER, "X-Warmup": "1"})
            print(f"      [Finamp items: {st3}] HTTP {c3} in {t3:.2f}s")


def main():
    try:
        lock_file = open(LOCK_FILE_PATH, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("Pre-warm is already running in the background. Skipping.")
        sys.exit(0)

    t_start = time.time()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting integrated Jellyfin Cache Pre-warming...")
    prewarm_dlna()
    prewarm_rest()
    total_time = time.time() - t_start
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Finished cache pre-warming in {total_time:.2f}s.")


if __name__ == "__main__":
    main()

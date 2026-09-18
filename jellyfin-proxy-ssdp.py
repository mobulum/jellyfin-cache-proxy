#!/usr/bin/env python3
"""
Lightweight SSDP Responder and Periodic Announcer for 'jellyfin-proxy'.
Listens on UDP 1900 for M-SEARCH requests and replies with jellyfin-proxy on port 8096.
Also broadcasts periodic NOTIFY (ssdp:alive) packets every 60 seconds.
"""

import socket
import struct
import time
import threading
import sys

MULTICAST_GROUP = "239.255.255.250"
SSDP_PORT = 1900
SERVER_IP = "192.168.2.251"
SERVER_PORT = 8096
LOCATION_URL = f"http://{SERVER_IP}:{SERVER_PORT}/jellyfin-proxy/description.xml"
DEVICE_UUID = "uuid:b70571c6-6ed8-5b7d-9b75-b7a43efc0cbe"
SERVER_NAME = "Linux/6.8 UPnP/1.0 JellyfinCacheProxy/1.0"

TARGETS = [
    ("upnp:rootdevice", f"{DEVICE_UUID}::upnp:rootdevice"),
    (DEVICE_UUID, DEVICE_UUID),
    ("urn:schemas-upnp-org:device:MediaServer:1", f"{DEVICE_UUID}::urn:schemas-upnp-org:device:MediaServer:1"),
    ("urn:schemas-upnp-org:service:ContentDirectory:1", f"{DEVICE_UUID}::urn:schemas-upnp-org:service:ContentDirectory:1"),
    ("urn:schemas-upnp-org:service:ConnectionManager:1", f"{DEVICE_UUID}::urn:schemas-upnp-org:service:ConnectionManager:1"),
]

def make_alive_notify(st, usn):
    return (
        f"NOTIFY * HTTP/1.1\r\n"
        f"HOST: {MULTICAST_GROUP}:{SSDP_PORT}\r\n"
        f"CACHE-CONTROL: max-age=1800\r\n"
        f"LOCATION: {LOCATION_URL}\r\n"
        f"NT: {st}\r\n"
        f"NTS: ssdp:alive\r\n"
        f"SERVER: {SERVER_NAME}\r\n"
        f"USN: {usn}\r\n"
        f"\r\n"
    ).encode("utf-8")

def make_msearch_response(st, usn):
    return (
        f"HTTP/1.1 200 OK\r\n"
        f"CACHE-CONTROL: max-age=1800\r\n"
        f"DATE: {time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime())}\r\n"
        f"EXT:\r\n"
        f"LOCATION: {LOCATION_URL}\r\n"
        f"SERVER: {SERVER_NAME}\r\n"
        f"ST: {st}\r\n"
        f"USN: {usn}\r\n"
        f"\r\n"
    ).encode("utf-8")

def announcer_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    while True:
        try:
            for st, usn in TARGETS:
                packet = make_alive_notify(st, usn)
                sock.sendto(packet, (MULTICAST_GROUP, SSDP_PORT))
                # Also send directly to Yamaha renderer if present
                try:
                    sock.sendto(packet, ("192.168.2.14", SSDP_PORT))
                except Exception:
                    pass
            time.sleep(60)
        except Exception as e:
            print(f"[Announcer] Error: {e}", file=sys.stderr)
            time.sleep(10)

def listener_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass

    sock.bind(("", SSDP_PORT))

    mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print(f"Jellyfin-proxy SSDP responder running on port {SSDP_PORT} for {LOCATION_URL}")

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            text = data.decode("utf-8", errors="ignore")
            lines = text.splitlines()
            if not lines:
                continue

            first_line = lines[0].strip().upper()
            if "M-SEARCH" not in first_line:
                continue

            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().upper()] = v.strip()

            man = headers.get("MAN", "").strip('"')
            if man.lower() != "ssdp:discover":
                continue

            st_req = headers.get("ST", "")

            # Match ST
            for st, usn in TARGETS:
                if st_req in ("ssdp:all", st, "upnp:rootdevice"):
                    resp = make_msearch_response(st, usn)
                    sock.sendto(resp, addr)

        except Exception as e:
            print(f"[Listener] Error: {e}", file=sys.stderr)

def main():
    t_announcer = threading.Thread(target=announcer_loop, daemon=True)
    t_announcer.start()
    listener_loop()

if __name__ == "__main__":
    main()

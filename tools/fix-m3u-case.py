#!/usr/bin/env python3
"""
Fix M3U Playlist Case Sensitivity Mismatches for Jellyfin.

Background:
Jellyfin's internal SQLite database (`BaseItems` table) stores file paths exactly as discovered during library scanning.
When Jellyfin resolves songs in M3U playlists, it queries the database with case-sensitive exact path matching.
If your music library is hosted on Windows/macOS/Samba/exFAT mounts (which are case-insensitive), files with casing
discrepancies (e.g., 'Various Artists' vs 'Various artists', or '.mp3' vs '.MP3') play fine on disk, but Jellyfin
silently drops them from playlists with:
  "Unable to find linked item at path ..."

This script matches each line of an M3U playlist against Jellyfin's actual `BaseItems` table in `jellyfin.db`
(case-insensitively) and rewrites the M3U playlist using the exact case Jellyfin indexed.
"""

import sys
import os
import sqlite3
import shutil

JELLYFIN_DB_DEFAULT = "/var/lib/jellyfin/data/jellyfin.db"

def fix_m3u_case(db_path, m3u_path):
    if not os.path.exists(db_path):
        print(f"Error: Jellyfin database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(m3u_path):
        print(f"Error: M3U file not found at {m3u_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to Jellyfin SQLite DB: {db_path}...")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()

    # Load all audio file paths from Jellyfin DB
    print("Loading indexed audio paths from Jellyfin database...")
    cursor.execute("SELECT Path FROM BaseItems WHERE MediaType = 'Audio' AND Path IS NOT NULL")
    
    # Map lowercase path -> canonical DB path
    db_paths = {}
    for (p,) in cursor.fetchall():
        db_paths[p.lower()] = p

    print(f"Indexed {len(db_paths)} audio files from database.")

    with open(m3u_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    modified = False
    fixed_count = 0
    not_found_count = 0
    new_lines = []

    m3u_dir = os.path.dirname(os.path.abspath(m3u_path))

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        # Handle relative or absolute paths
        target_path = stripped
        if not os.path.isabs(target_path):
            target_path = os.path.normpath(os.path.join(m3u_dir, target_path))

        lower_target = target_path.lower()
        if lower_target in db_paths:
            canonical = db_paths[lower_target]
            if canonical != stripped:
                # If original was relative, convert canonical back to relative if desired,
                # or keep relative path casing aligned.
                if not os.path.isabs(stripped):
                    canonical_rel = os.path.relpath(canonical, m3u_dir)
                    new_lines.append(canonical_rel + "\n")
                else:
                    new_lines.append(canonical + "\n")
                fixed_count += 1
                modified = True
            else:
                new_lines.append(line)
        else:
            not_found_count += 1
            new_lines.append(line)

    conn.close()

    print(f"Results for '{m3u_path}':")
    print(f"  Fixed case mismatches : {fixed_count}")
    print(f"  Paths not in DB index : {not_found_count}")

    if modified:
        backup_path = f"{m3u_path}.casefix_bak"
        print(f"Creating backup: {backup_path}")
        shutil.copy2(m3u_path, backup_path)
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print("Updated playlist with canonical database paths successfully.")
    else:
        print("No casing mismatches found in playlist.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fix-m3u-case.py <path-to-playlist.m3u> [path-to-jellyfin.db]")
        sys.exit(1)

    m3u_file = sys.argv[1]
    db_file = sys.argv[2] if len(sys.argv) > 2 else JELLYFIN_DB_DEFAULT

    fix_m3u_case(db_file, m3u_file)

if __name__ == "__main__":
    main()

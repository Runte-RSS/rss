#!/usr/bin/env python3
"""
prune_feed.py

Usage:
  python prune_feed.py --rss rss.xml --seen seen.json --days 14 [--dry-run] [--debug]

Removes <item> entries from rss.xml older than --days only when that series
has a newer item within the window. Also removes matching entries from seen.json.
Backups: rss.xml.bak and seen.json.bak are created before writing.
"""
from __future__ import annotations
import os
import re
import json
import shutil
import argparse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

def _backup_file(path):
    if os.path.exists(path):
        bak = path + ".bak"
        shutil.copy2(path, bak)

def series_key_from_url_or_guid(link_or_guid: str) -> str:
    if not link_or_guid:
        return ""
    try:
        p = urlparse(link_or_guid)
        if p.scheme and p.netloc:
            path = p.path.rstrip('/')
            path = re.sub(r'/(?:chapter|chap|c|read|page)[^/]*$', '', path, flags=re.IGNORECASE)
            path = re.sub(r'/\d+(?:\.\d+)?$', '', path)
            return f"{p.scheme}://{p.netloc}{path}"
    except Exception:
        pass
    if '|' in link_or_guid:
        return link_or_guid.split('|', 1)[0]
    if ':' in link_or_guid:
        return link_or_guid.rsplit(':', 1)[0]
    return link_or_guid

def prune_rss_conditional(rss_file: str, seen_file: str, max_age_days: int = 14, dry_run: bool = False, debug: bool = False):
    if not os.path.exists(rss_file):
        if debug: print("rss file not found:", rss_file)
        return {"rss_removed": [], "seen_removed": []}

    tree = ET.parse(rss_file)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        channel = root.find("{http://purl.org/rss/1.0/}channel")
    if channel is None:
        if debug: print("No channel element found in rss file")
        return {"rss_removed": [], "seen_removed": []}

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    groups = {}
    items = channel.findall("item")
    for item in items:
        pub_el = item.find("pubDate")
        guid_el = item.find("guid")
        link_el = item.find("link")
        identifier = None
        if guid_el is not None and guid_el.text:
            identifier = guid_el.text.strip()
        elif link_el is not None and link_el.text:
            identifier = link_el.text.strip()
        else:
            title_el = item.find("title")
            identifier = (title_el.text.strip() if title_el is not None and title_el.text else f"item-{len(groups)}")

        pub_dt = None
        if pub_el is not None and pub_el.text:
            try:
                pub_dt = parsedate_to_datetime(pub_el.text)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pub_dt = None

        series_source = (link_el.text.strip() if link_el is not None and link_el.text else identifier)
        sk = series_key_from_url_or_guid(series_source)
        groups.setdefault(sk, []).append({"el": item, "pub_dt": pub_dt, "id": identifier})

    to_remove_ids = []
    to_remove_elements = []
    for sk, entries in groups.items():
        newest = None
        for e in entries:
            if e["pub_dt"] is not None:
                if newest is None or e["pub_dt"] > newest:
                    newest = e["pub_dt"]

        if newest is None:
            if debug: print("Skipping series (no dated items):", sk)
            continue

        if newest < cutoff:
            if debug: print("Skipping series (newest older than cutoff):", sk, "newest:", newest.isoformat())
            continue

        for e in entries:
            if e["pub_dt"] is None:
                continue
            if e["pub_dt"] < cutoff:
                to_remove_ids.append(e["id"])
                to_remove_elements.append(e["el"])
                if debug: print("Marking for removal:", e["id"], "pub", e["pub_dt"].isoformat())

    if not dry_run and to_remove_elements:
        _backup_file(rss_file)
        for el in to_remove_elements:
            channel.remove(el)
        tree.write(rss_file, encoding="utf-8", xml_declaration=True)

    removed_seen = []
    if os.path.exists(seen_file):
        with open(seen_file, "r", encoding="utf-8") as f:
            try:
                seen_data = json.load(f)
            except Exception:
                seen_data = {"items": []}
        items_raw = seen_data.get("items", seen_data)
        normalized = []
        orig_was_list_of_strings = all(isinstance(x, str) for x in items_raw)
        for it in items_raw:
            if isinstance(it, str):
                normalized.append({"guid": it, "seen_at": None})
            elif isinstance(it, dict):
                normalized.append({"guid": it.get("guid"), "seen_at": it.get("seen_at")})
        kept = []
        for it in normalized:
            if it["guid"] in to_remove_ids:
                removed_seen.append(it["guid"])
                if debug: print("Removing seen entry:", it["guid"])
            else:
                kept.append(it)
        if not dry_run and removed_seen:
            _backup_file(seen_file)
            if orig_was_list_of_strings:
                out = {"items": [it["guid"] for it in kept]}
            else:
                out = {"items": kept}
            with open(seen_file, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)

    return {"rss_removed": to_remove_ids, "seen_removed": removed_seen}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rss", required=True, help="Path to rss.xml")
    p.add_argument("--seen", required=True, help="Path to seen.json")
    p.add_argument("--days", type=int, default=14, help="Max age in days")
    p.add_argument("--dry-run", action="store_true", help="Do not write changes")
    p.add_argument("--debug", action="store_true", help="Verbose logging")
    args = p.parse_args()

    res = prune_rss_conditional(args.rss, args.seen, max_age_days=args.days, dry_run=args.dry_run, debug=args.debug)
    if args.debug or args.dry_run:
        print("Result:", res)
    # exit code 0 always; workflow will check git diff to decide commit
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

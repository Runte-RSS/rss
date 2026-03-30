#!/usr/bin/env python3
"""
Conservative remove_empty_items.py

Removes only items where title, link, description, and guid are ALL empty.
Usage:
  python remove_empty_items.py --rss rss.xml --seen seen.json [--dry-run]
"""
import argparse
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

def backup(path):
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
        print(f"Backed up {path} -> {path}.bak")

def load_seen(seen_path):
    if not os.path.exists(seen_path):
        return []
    with open(seen_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            return []
    # Support two shapes: list of strings or {"items": [...]}
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, list):
        return data
    return []

def write_seen(seen_path, items):
    # Preserve original shape as a simple list
    with open(seen_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"Wrote seen.json ({len(items)} entries)")

def text_of(el):
    if el is None:
        return ""
    return (el.text or "").strip()

def run(rss_path, seen_path, dry_run):
    # Parse XML (let exceptions bubble up so caller sees parse errors)
    tree = ET.parse(rss_path)
    root = tree.getroot()
    channel = root.find('channel')
    if channel is None:
        print("No <channel> element found; aborting.")
        sys.exit(2)

    # Collect items to remove
    to_remove = []
    for item in channel.findall('item'):
        title = text_of(item.find('title'))
        link = text_of(item.find('link'))
        desc = text_of(item.find('description'))
        guid_el = item.find('guid')
        guid = text_of(guid_el) if guid_el is not None else ""

        # Conservative rule: remove only if ALL are empty
        if not (title or link or desc or guid):
            # capture some context for logging
            to_remove.append({
                "item": item,
                "guid": guid or None,
                "link": link or None,
            })

    print(f"Found {len(to_remove)} candidate empty items (conservative rule)")

    if dry_run:
        if to_remove:
            print("Dry-run: the following items would be removed:")
            for i, info in enumerate(to_remove, 1):
                print(f" {i}. guid={info['guid']}, link={info['link']}")
        else:
            print("Dry-run: no items to remove")
        return

    if not to_remove:
        print("No items to remove; exiting.")
        return

    # Backup before modifying
    backup(rss_path)
    backup(seen_path)

    # Remove items and collect GUIDs removed
    removed_guids = []
    for info in to_remove:
        item = info["item"]
        guid_text = info["guid"]
        channel.remove(item)
        if guid_text:
            removed_guids.append(guid_text)

    # Write updated RSS
    tree.write(rss_path, encoding='utf-8', xml_declaration=True)
    print(f"Removed {len(to_remove)} items from {rss_path}")

    # Prune seen.json: remove any removed GUIDs from seen list
    if os.path.exists(seen_path) and removed_guids:
        seen_list = load_seen(seen_path)
        # If seen_list is list of dicts or strings, normalize to strings if possible
        normalized = []
        if all(isinstance(x, str) for x in seen_list):
            normalized = seen_list
            kept = [g for g in normalized if g not in removed_guids]
            write_seen(seen_path, kept)
        else:
            # If items are objects with 'guid' keys, preserve structure
            kept_objs = []
            for it in seen_list:
                if isinstance(it, dict):
                    if it.get('guid') not in removed_guids:
                        kept_objs.append(it)
                elif isinstance(it, str):
                    if it not in removed_guids:
                        kept_objs.append(it)
            # Write back in the same top-level shape as before if it was dict with items
            # We will write a simple list if original was list-like
            write_seen(seen_path, kept_objs)
        print(f"Pruned {len(removed_guids)} GUIDs from {seen_path}")
    else:
        print("No seen.json pruning needed")

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rss', required=True, help='Path to rss.xml')
    p.add_argument('--seen', required=True, help='Path to seen.json')
    p.add_argument('--dry-run', action='store_true', help='Show what would be removed')
    args = p.parse_args()
    try:
        run(args.rss, args.seen, args.dry_run)
    except ET.ParseError as e:
        print("XML parse error:", e)
        sys.exit(1)
    except Exception as e:
        print("Unexpected error:", e)
        sys.exit(2)

if __name__ == '__main__':
    main()

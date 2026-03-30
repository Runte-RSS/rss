#!/usr/bin/env python3
"""
remove_empty_items.py
Removes items with empty title/link/description from rss.xml and matching seen.json entries.
Usage:
  python remove_empty_items.py --rss rss.xml --seen seen.json [--dry-run]
"""
import argparse, json, shutil, os, re, sys
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ParseError

def backup(p):
    if os.path.exists(p):
        shutil.copy2(p, p + ".bak")

def safe_parse_xml(path):
    # Try normal parse first
    try:
        return ET.parse(path)
    except ParseError as e:
        print(f"Initial XML parse failed: {e}")
    except Exception as e:
        print(f"Initial XML parse unexpected error: {e}")

    # Try to repair: read as text, remove control chars except \t\n\r, strip leading garbage before <?xml
    try:
        with open(path, "rb") as f:
            raw = f.read()
        # Try decode as utf-8 with replacement to avoid decode errors
        text = raw.decode("utf-8", errors="replace")
        # Remove C0 control chars except tab/newline/carriage return
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        # If file contains garbage before XML declaration, strip everything before first '<'
        first_lt = text.find('<')
        if first_lt > 0:
            print(f"Stripping {first_lt} leading bytes before first '<'")
            text = text[first_lt:]
        # Ensure it starts with <?xml or <rss or <feed
        if not re.match(r'^\s*<\?xml|^\s*<rss|^\s*<feed', text, flags=re.I):
            print("Repaired text does not start with XML root; aborting repair.")
            raise ParseError("Repaired text missing XML root")
        # Write to a temp file and try parse
        tmp = path + ".repair.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            tree = ET.parse(tmp)
            print("Repair parse succeeded; will use repaired content.")
            # overwrite original with repaired content (but keep backup)
            backup(path)
            shutil.move(tmp, path)
            return ET.parse(path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    except ParseError as e:
        print("Repair attempt failed:", e)
    except Exception as e:
        print("Repair attempt unexpected error:", e)

    # If we reach here, parsing failed
    raise SystemExit(2)

def run(rss, seen, dry):
    tree = safe_parse_xml(rss)
    root = tree.getroot()
    channel = root.find('channel')
    if channel is None:
        # try namespace fallback
        channel = root.find('{http://purl.org/rss/1.0/}channel')
    if channel is None:
        print("No channel element found; aborting.")
        raise SystemExit(3)

    to_remove = []
    for item in channel.findall('item'):
        title = (item.find('title').text or '').strip() if item.find('title') is not None else ''
        link = (item.find('link').text or '').strip() if item.find('link') is not None else ''
        desc = (item.find('description').text or '').strip() if item.find('description') is not None else ''
        if not (title or link or desc):
            guid = item.find('guid').text if item.find('guid') is not None else None
            to_remove.append((item, guid))

    print("Found", len(to_remove), "empty items")
    if dry:
        for _,g in to_remove:
            print("Would remove guid:", g)
        return

    backup(rss); backup(seen)
    removed_guids = []
    for item,guid in to_remove:
        channel.remove(item)
        if guid:
            removed_guids.append(guid)
    tree.write(rss, encoding='utf-8', xml_declaration=True)
    # prune seen.json
    if os.path.exists(seen):
        with open(seen,'r',encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception:
                data = {"items": []}
        items = data.get('items', data)
        orig_list_of_strings = all(isinstance(x,str) for x in items)
        normalized = []
        for it in items:
            if isinstance(it,str):
                normalized.append({'guid':it,'seen_at':None})
            else:
                normalized.append({'guid':it.get('guid'),'seen_at':it.get('seen_at')})
        kept = [it for it in normalized if it['guid'] not in removed_guids]
        out = {'items':[it['guid'] for it in kept]} if orig_list_of_strings else {'items':kept}
        with open(seen,'w',encoding='utf-8') as f:
            json.dump(out,f,indent=2,ensure_ascii=False)
    print("Removed", len(removed_guids), "seen entries")

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--rss', required=True)
    p.add_argument('--seen', required=True)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    run(args.rss, args.seen, args.dry_run)

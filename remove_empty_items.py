#!/usr/bin/env python3
import argparse, json, shutil, os
import xml.etree.ElementTree as ET

def backup(p):
    if os.path.exists(p):
        shutil.copy2(p, p + ".bak")

def run(rss, seen, dry):
    tree = ET.parse(rss)
    ch = tree.getroot().find('channel')
    to_remove = []
    for item in ch.findall('item'):
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
        ch.remove(item)
        if guid:
            removed_guids.append(guid)
    tree.write(rss, encoding='utf-8', xml_declaration=True)
    # prune seen.json
    if os.path.exists(seen):
        with open(seen,'r',encoding='utf-8') as f:
            data = json.load(f)
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

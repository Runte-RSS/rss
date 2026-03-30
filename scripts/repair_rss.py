#!/usr/bin/env python3
# scripts/repair_rss.py
import xml.etree.ElementTree as ET, shutil, os
from urllib.parse import urlparse

# Load SITES mapping inline or import from your config
SITES = [
    {"title":"One Piece","url":"https://tcbonepiecechapters.com/mangas/5/one-piece","image":"https://cdn.onepiecechapters.com/...png"},
    # add other entries or import your SITES
]

def domain(u):
    try:
        return urlparse(u).netloc.lower()
    except:
        return ''

def find_site(link):
    d = domain(link or '')
    for s in SITES:
        if domain(s['url']) == d:
            return s
    for s in SITES:
        if s['url'].rstrip('/') in (link or ''):
            return s
    return None

rss = 'rss.xml'
bak = rss + '.repair.bak'
shutil.copy2(rss, bak)
print('Backed up', rss, '->', bak)

# Parse robustly; if parse fails, try to trim after the last closing </rss>
try:
    tree = ET.parse(rss)
except ET.ParseError:
    print('ParseError: attempting to trim after last </rss>')
    data = open(rss,'rb').read()
    idx = data.rfind(b'</rss>')
    if idx == -1:
        raise
    trimmed = data[:idx+6]
    open(rss,'wb').write(trimmed)
    tree = ET.parse(rss)
    print('Trimmed file to last </rss> and reparsed')

root = tree.getroot()
channel = root.find('channel')
changed = 0
for item in channel.findall('item'):
    t = item.find('title')
    title_text = (t.text or '').strip() if t is not None else ''
    if not title_text:
        link_el = item.find('link')
        link = link_el.text.strip() if link_el is not None and link_el.text else None
        site = find_site(link)
        if site and site.get('title'):
            if t is None:
                t = ET.SubElement(item, 'title')
            t.text = site['title']
            changed += 1
            print('Filled title from SITES for', link, '->', site['title'])
        else:
            # fallback: generate from URL path
            if link:
                parts = link.rstrip('/').split('/')
                fallback = ' — '.join([p.replace('-', ' ').title() for p in parts[-2:]])
                if t is None:
                    t = ET.SubElement(item, 'title')
                t.text = fallback
                changed += 1
                print('Generated fallback title for', link, '->', fallback)

if changed:
    tree.write('rss.fixed.xml', encoding='utf-8', xml_declaration=True)
    os.replace('rss.fixed.xml', rss)
    print('Wrote fixed rss.xml (changed {})'.format(changed))
else:
    print('No title changes needed')

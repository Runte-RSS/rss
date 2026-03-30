#!/usr/bin/env python3
# scripts/fill_titles.py
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import requests, re, json, shutil, time, os

# Load SITES from your config file or inline here
SITES = [
    {"title":"One Piece","url":"https://tcbonepiecechapters.com/mangas/5/one-piece","image":"https://cdn.onepiecechapters.com/...png"},
    # add other site entries or import from your generator config
]

def domain_of(u):
    try:
        return urlparse(u).netloc.lower()
    except:
        return ''

def find_site_for_link(link):
    d = domain_of(link)
    # first try domain match
    for s in SITES:
        if domain_of(s['url']) == d:
            return s
    # then substring match
    for s in SITES:
        if s['url'].rstrip('/') in link:
            return s
    return None

def fetch_page_title(url):
    try:
        r = requests.get(url, timeout=8, headers={'User-Agent':'Mozilla/5.0'})
        if r.status_code != 200:
            return None
        m = re.search(r'<title[^>]*>(.*?)</title>', r.text, flags=re.I|re.S)
        if m:
            return re.sub(r'\s+',' ', m.group(1)).strip()
    except Exception:
        return None
    return None

def main():
    rss = 'rss.xml'
    bak = rss + '.bak'
    if os.path.exists(rss):
        shutil.copy2(rss, bak)
    tree = ET.parse(rss)
    root = tree.getroot()
    channel = root.find('channel')
    changed = 0
    for item in channel.findall('item'):
        title_el = item.find('title')
        title_text = (title_el.text or '').strip() if title_el is not None else ''
        if title_text:
            continue
        link_el = item.find('link')
        link = link_el.text.strip() if link_el is not None and link_el.text else None
        new_title = None
        if link:
            site = find_site_for_link(link)
            if site and site.get('title'):
                new_title = site['title']
            else:
                new_title = fetch_page_title(link)
                time.sleep(0.5)
        if new_title:
            if title_el is None:
                title_el = ET.SubElement(item, 'title')
            title_el.text = new_title
            changed += 1
            print('Filled title for', link, '->', new_title)
    if changed:
        tree.write('rss.fixed.xml', encoding='utf-8', xml_declaration=True)
        print('Wrote rss.fixed.xml (changed {})'.format(changed))
    else:
        print('No changes made')

if __name__ == '__main__':
    main()

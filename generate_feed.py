#!/usr/bin/env python3
# generate_feed.py
# Simple RSS generator for Fluent Reader. Add sites to SITES list.

import re
from dateutil import parser as dateparser   # add python-dateutil to requirements.txt
import json
import os
import hashlib
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from xml.sax.saxutils import escape

RSS_FILE = "rss.xml"
SEEN_FILE = "seen.json"
MAX_ITEMS = 50
USER_AGENT = "Mozilla/5.0 (compatible; rss-bot/1.0; +https://example.com/)"

# Add sites here. Each entry needs: title, url (manga page), image (thumbnail)
SITES = [
    {
        "title": "One Piece",
        "url": "https://tcbonepiecechapters.com/mangas/5/one-piece",
        "image": "https://cdn.onepiecechapters.com/file/CDN-M-A-N/Screen-Shot-2021-04-23-at-9.31.12-PM-1024x732v3.png",
    },{
        "title": "Shut Up, Evil Dragon! I don’t want to raise a child with you anymore",
        "url": "https://manhuabuddy.com/manhwa/shut-up-evil-dragon-i-dont-want-to-raise-a-child-with-you-anymore",
        "image": "https://media.manhuabuddy.com/files/images/thumbs/shut-up-evil-dragon-i-dont-want-to-raise-a-child-with-you-anymore.webp",
    },{
        "title": "Transmigrating Into The Cyber Game After Being On Top For Killing Boss",
        "url": "https://mangamirror.com/manga/121372-transmigrating-into-the-cyber-game-after-being-on-top-for-killing-boss",
        "image": "https://cdn.anime-planet.com/manga/primary/after-transmigrating-into-the-cyberpunk-game-i-defeated-the-boss-and-successfully-rose-to-the-top-1.webp?t=1759754015",
    },{
        "title": "I Played the Role of the Adopted Daughter Too Well",
        "url": "https://mangamirror.com/manga/50583-i-played-the-role-of-the-adopted-daughter-too-well",
        "image": "https://www.mangaread.org/wp-content/uploads/2023/09/28-1677642819-193x278.jpg",
    },
    # Example: add more sites below
    # {
    #   "title": "Another Manga",
    #   "url": "https://example.com/manga/slug",
    #   "image": "https://example.com/thumb.png",
    # },
]

HEADERS = {"User-Agent": USER_AGENT}
CHAPTER_HREF_RE = re.compile(r"/chapters/(\d+)", re.IGNORECASE)
CHAPTER_NUM_RE = re.compile(r"chapter[-\s]?(\d+)", re.IGNORECASE)

def parse_chap_num(text):
    """
    Return a numeric chapter value for sorting (float), or -1.0 if none found.
    Handles integers and decimals like "12" or "12.5".
    """
    m = re.search(r'(\d+(?:\.\d+)?)', text)
    return float(m.group(1)) if m else -1.0


def extract_thumbnail(page_url):
    r = requests.get(page_url, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    # 1) prefer og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urljoin(page_url, og["content"].strip())

    # 2) link rel=image_src
    link_img = soup.find("link", rel="image_src")
    if link_img and link_img.get("href"):
        return urljoin(page_url, link_img["href"].strip())

    # 3) check img tags for data-src/data-original/src
    for img in soup.find_all("img"):
        for attr in ("data-src", "data-original", "src"):
            val = img.get(attr)
            if val and val.strip() and "placeholder" not in val:
                return urljoin(page_url, val.strip())

    return None
def now_rfc2822():
    return format_datetime(datetime.now(timezone.utc))

def make_guid(text):
    return "urn:sha1:" + hashlib.sha1(text.encode("utf-8")).hexdigest()

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"items": []}
    return {"items": []}

def save_seen(data):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def http_get(url, timeout=20):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text

def normalize_url(u):
    return u.rstrip('/')

from urllib.parse import urlparse, urljoin

def find_latest_chapter(page_url, title=None):
    html = http_get(page_url)
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    expected_slug = urlparse(page_url).path.strip('/').split('/')[-1]

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(page_url, href)
        text = a.get_text(" ", strip=True) or ""

        # Only consider links that look like chapter links
        if not (re.search(r"chapter|chap|ch\b|/read/|/manga/", full, re.IGNORECASE) or
                re.search(r"chapter|chap|ch\b", text, re.IGNORECASE)):
            continue

        # Try to extract a numeric chapter value (allow decimals)
        chap_num = None
        m_url = re.findall(r"(\d+(?:\.\d+)?)", full)
        if m_url:
            try:
                chap_num = float(m_url[-1])
            except Exception:
                chap_num = None

        if chap_num is None:
            pn = parse_chap_num(text)
            if pn is not None and pn != -1.0:
                chap_num = pn

        if chap_num is None or chap_num == -1.0:
            m2 = CHAPTER_HREF_RE.search(href) or CHAPTER_NUM_RE.search(text)
            if m2:
                try:
                    chap_num = float(m2.group(1))
                except Exception:
                    chap_num = None

        if chap_num is None:
            continue

        # Filter out links that clearly point to other manga pages
        if expected_slug and expected_slug not in full:
            title_words = [w.lower() for w in (title or "").split()[:3]]
            if not any(w for w in title_words if w and w in text.lower()):
                continue

        # Boost links whose anchor text contains the manga title words
        boost = 0.1 if title and any(w.lower() in text.lower() for w in title.split()[:3]) else 0.0

        candidates.append({
            "url": normalize_url(full),
            "text": text,
            "score": chap_num + boost
        })

    if not candidates:
        return None

    best = max(candidates, key=lambda x: x["score"])

    # Follow redirects and normalize final URL
    try:
        r = requests.get(best["url"], headers=HEADERS, timeout=10)
        final_url = normalize_url(r.url)
    except Exception:
        final_url = normalize_url(best["url"])

    best["url"] = final_url
    return best

    
    

    # optional debug: print top candidates
    # candidates_sorted = sorted(candidates, key=lambda x: x['score'], reverse=True)
    # print("DEBUG candidates:", [(c['score'], c['url']) for c in candidates_sorted[:5]])

    best = max(candidates, key=lambda x: x["score"])
    return best




def normalize_item(it):
    now = now_rfc2822()
    return {
        "title": it.get("title", ""),
        "link": it.get("link", ""),
        "guid": it.get("guid", make_guid(it.get("title","") + "|" + it.get("link",""))),
        "pubDate": it.get("pubDate", now),
        "description": it.get("description", ""),
        "image": it.get("image", ""),
    }

def write_rss(channel_title, channel_link, channel_desc, items, out_file):
    items = items[:MAX_ITEMS]
    header = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">\n'
        "  <channel>\n"
        f"    <title>{escape(channel_title)}</title>\n"
        f"    <link>{escape(channel_link)}</link>\n"
        f"    <description>{escape(channel_desc)}</description>\n"
        f"    <lastBuildDate>{now_rfc2822()}</lastBuildDate>\n"
    )
    items_xml = ""
    for it in items:
        items_xml += "    <item>\n"
        items_xml += f"      <title>{escape(it.get('title',''))}</title>\n"
        items_xml += f"      <link>{escape(it.get('link',''))}</link>\n"
        items_xml += f"      <guid isPermaLink=\"false\">{escape(it.get('guid',''))}</guid>\n"
        items_xml += f"      <pubDate>{escape(it.get('pubDate',''))}</pubDate>\n"
        if it.get("image"):
            items_xml += f"      <media:thumbnail url=\"{escape(it['image'])}\" />\n"
            items_xml += f"      <enclosure url=\"{escape(it['image'])}\" type=\"image/jpeg\" />\n"
        items_xml += f"      <description><![CDATA[{it.get('description','')}]]></description>\n"
        items_xml += "    </item>\n"
    footer = "  </channel>\n</rss>\n"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(header + items_xml + footer)

def main():
    seen = load_seen()
    history = seen.get("items", [])
    if not isinstance(history, list):
        history = []

    for site in SITES:
        title = site.get("title")
        page = site.get("url")
        thumb = site.get("image", "")
        print(f"Checking {title} -> {page}")
        try:
            latest = find_latest_chapter(page, title)
        except Exception as e:
            print("  Error scraping:", e)
            latest = None

        if not latest:
            print("  No chapter links found; skipping.")
            # normalize any existing entry for this title
            for i, it in enumerate(history):
                if it.get("title") == title:
                    history[i] = normalize_item(it)
            continue

        chapter_url = latest["url"]
        score = latest["score"]
        guid = make_guid(f"{title}|{score}|{chapter_url}")

        already = any(it.get("guid") == guid for it in history)
        if already:
            print("  No new chapter.")
            # update existing entry link/image/pubDate if needed
            for i, it in enumerate(history):
                if it.get("title") == title or it.get("guid") == guid:
                    it["link"] = chapter_url
                    it["image"] = thumb
                    it["pubDate"] = it.get("pubDate", now_rfc2822())
                    history[i] = normalize_item(it)
            continue

        # new chapter -> prepend
        pubDate = now_rfc2822()
        description = (
            f'<a href="{escape(chapter_url)}">'
            f'<img src="{escape(thumb)}" alt="{escape(title)}" style="max-width:200px;height:auto;display:block;margin-bottom:8px;" />'
            f'</a>'
            f'<div><a href="{escape(page)}">{escape(title)}</a><br/>{escape(latest.get("text",""))}</div>'
        )
        item = {
            "title": f"{title} — new chapter",
            "link": chapter_url,
            "guid": guid,
            "pubDate": pubDate,
            "description": description,
            "image": thumb,
        }
        print("  New chapter detected:", chapter_url)
        history.insert(0, normalize_item(item))

    history = [normalize_item(it) for it in history][:MAX_ITEMS]
    seen["items"] = history
    save_seen(seen)

    write_rss(
        channel_title="My Manga Watchlist",
        channel_link="https://example.com/",
        channel_desc="Auto-generated manga feed for Fluent Reader",
        items=history,
        out_file=RSS_FILE,
    )
    print(f"Wrote {RSS_FILE} with {len(history)} items.")

if __name__ == "__main__":
    main()

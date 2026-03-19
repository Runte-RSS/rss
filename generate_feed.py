#!/usr/bin/env python3
# generate_feed.py
# Simple RSS generator for Fluent Reader. Add sites to SITES list.

import re
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

def find_latest_chapter(page_url):
    html = http_get(page_url)
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(page_url, href)
        if "/chapters/" not in full:
            continue
        text = a.get_text(" ", strip=True) or ""
        m_id = CHAPTER_HREF_RE.search(full)
        chap_id = int(m_id.group(1)) if m_id else None
        m_num = CHAPTER_NUM_RE.search(full) or CHAPTER_NUM_RE.search(text)
        chap_num = int(m_num.group(1)) if m_num else None
        score = chap_id if chap_id is not None else chap_num
        if score is None:
            continue
        candidates.append({"url": full, "text": text, "score": score})
    if not candidates:
        return None
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
            latest = find_latest_chapter(page)
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

#!/usr/bin/env python3
# generate_feed.py
# Simple RSS generator for Fluent Reader. Add sites to SITES list.

import re
from dateutil import parser as dateparser
import json
import os
import hashlib
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from xml.sax.saxutils import escape
import cloudscraper
import time
import random


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
        "url": "https://mangamirror.com/manga/122851-shut-up-evil-dragon-i-dont-want-to-raise-a-child-with-you-anymore",
        "image": "https://media.manhuabuddy.com/files/images/thumbs/shut-up-evil-dragon-i-dont-want-to-raise-a-child-with-you-anymore.webp",
    },{
        "title": "Transmigrating Into The Cyber Game After Being On Top For Killing Boss",
        "url": "https://mangamirror.com/manga/121372-transmigrating-into-the-cyber-game-after-being-on-top-for-killing-boss",
        "image": "https://cdn.anime-planet.com/manga/primary/after-transmigrating-into-the-cyberpunk-game-i-defeated-the-boss-and-successfully-rose-to-the-top-1.webp?t=1759754015",
    },{
        "title": "I Played the Role of the Adopted Daughter Too Well",
        "url": "https://mangamirror.com/manga/50583-i-played-the-role-of-the-adopted-daughter-too-well",
        "image": "https://www.mangaread.org/wp-content/uploads/2023/09/28-1677642819-193x278.jpg",
    },{
        "title": "The Fox-Eyed Villain of the Demon Academy",
        "url": "https://mangamirror.com/manga/127739-the-fox-eyed-villain-of-the-demon-academy",
        "image": "https://static.asurascans.my/book/f47aadb5-8bff-4ba1-bece-66f0ec681c24/cover/b54fe4a9-a71f-400c-929a-2b1ef9b4c7dd.webp?width=400&type=webp",
    },{
        "title": "Revenge Of The Sword Clan's Hound",
        "url": "https://mangamirror.com/manga/59511-revenge-of-the-sword-clans-hound",
        "image": "https://bulbasaur.poke-black-and-white.net/covers/6851547b702284f834178357/cover_1752077533539.webp",
    },{
        "title": "The Billionaire’s Replacement Wife",
        "url": "https://mangamirror.com/manga/95801-the-billionaires-replacement-wife",
        "image": "https://us-a.tapas.io/sa/76/2546a686-8b25-4e18-bdb5-2306567d34da.jpg",
    },{
        "title": "Black Killer Whale Baby",
        "url": "https://mangamirror.com/manga/119653-black-killer-whale-baby",
        "image": "https://cdn.novelupdates.com/images/2023/06/Black-Killer-Whale-Baby.jpg",
    },{
        "title": "Don't Expect Me to Take Responsibility",
        "url": "https://mangamirror.com/manga/132868-dont-expect-me-to-take-responsibility",
        "image": "https://puu.sh/KKikc.png",
    },
    # Example: add more sites below
    # {
    #   "title": "Another Manga",
    #   "url": "https://example.com/manga/slug",
    #   "image": "https://example.com/thumb.png",
    # },
]
# --- headers and session (module-level, safe) ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://google.com/",
}

session = requests.Session()
session.headers.update(HEADERS)

# configure retries (safe defaults)
retries = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"]
)
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

# --- helper fetch function (use everywhere instead of session.get directly) ---
def fetch_url(url, timeout=15, allow_cloudscraper=True, debug=False):
    # small jitter to avoid bursts from CI
    time.sleep(random.uniform(0.3, 1.2))
    try:
        # <-- use session.get here (was incorrectly calling fetch_url recursively)
        r = fetch_url(url, timeout=15, allow_cloudscraper=True, debug=True)
        r.raise_for_status()
        return r
    except Exception as e:
        if debug:
            print("fetch_url: requests failed for", url, "error:", repr(e))
            if hasattr(e, "response") and e.response is not None:
                print("Response head:", e.response.status_code, e.response.headers)
                print(e.response.text[:1000])
        if allow_cloudscraper:
            try:
                scraper = cloudscraper.create_scraper(browser={'custom': HEADERS['User-Agent']})
                r2 = scraper.get(url, timeout=timeout, allow_redirects=True)
                r2.raise_for_status()
                return r2
            except Exception as e2:
                if debug:
                    print("fetch_url: cloudscraper fallback failed for", url, "error:", repr(e2))
                raise
        raise


def parse_chap_num(text):
    """
    Return a numeric chapter value for sorting (float), or -1.0 if none found.
    Handles integers and decimals like "12" or "12.5".
    """
    m = re.search(r'(\d+(?:\.\d+)?)', text)
    return float(m.group(1)) if m else -1.0


def extract_thumbnail(page_url):
    r = fetch_url(url, timeout=15, allow_cloudscraper=True, debug=True)
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
    r = fetch_url(url, timeout=15, allow_cloudscraper=True, debug=True)
    r.raise_for_status()
    return r.text

def normalize_url(u):
    return u.rstrip('/')

from urllib.parse import urlparse, urljoin

ID_RE = re.compile(r"/manga/(\d+)[-/]?", re.IGNORECASE)

def find_latest_chapter(page_url, title=None, debug=False):
    # fetch page and follow redirects so we use canonical URL
    try:
        r = fetch_url(url, timeout=15, allow_cloudscraper=True, debug=True)
        rpage.raise_for_status()
        page_html = rpage.text
        canonical_page_url = normalize_url(rpage.url)
    except Exception:
        page_html = http_get(page_url)
        canonical_page_url = normalize_url(page_url)

    soup = BeautifulSoup(page_html, "html.parser")
    candidates = []

    # extract numeric id from canonical page URL
    m_id = ID_RE.search(canonical_page_url)
    expected_id = m_id.group(1) if m_id else None

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(canonical_page_url, href)
        text = a.get_text(" ", strip=True) or ""

                # quick filter for likely chapter links
        # allow if URL or text contains explicit chapter/read markers
                # quick filter for likely chapter links
        is_chapter_url = bool(re.search(r"(?:/chapter/|/read/|/c/|chapter-|chap-|\bchapter\b|\bchap\b|\bch\b|/page/)", full, re.IGNORECASE))
        is_chapter_text = bool(re.search(r"(?:chapter|chap|ch)\s*\d", text, re.IGNORECASE))

        # detect plain listing pages like /manga/slug or /manhwa/slug-2025 (not chapter pages)
        is_listing_page = bool(re.search(r"/(?:manga|manhwa|manhua)/[^/]+(?:$|/|[-]\d{4}(?:$|/))", full, re.IGNORECASE))

        # If it's a plain listing page and not explicitly a chapter link by URL or text, skip it
        if is_listing_page and not (is_chapter_url or is_chapter_text):
            continue

        # If it is neither a chapter-like URL nor chapter-like text nor contains any digit, skip it
        if not (is_chapter_url or is_chapter_text or re.search(r"\d", full)):
            continue



                # --- improved chapter number extraction ---
                # improved chapter number extraction
        chap_num = None

        # all numeric tokens in the URL (in order)
                # all numeric tokens in the URL (in order)
        url_nums = re.findall(r"(\d+(?:\.\d+)?)", full)

        # helper tests
        def is_year_token(n):
            try:
                v = int(float(n))
                return 1900 <= v <= 2100
            except Exception:
                return False

        def is_timestamp_token(n):
            try:
                v = int(float(n))
                return v >= 1_000_000_000  # 10-digit epoch-like numbers
            except Exception:
                return False

        # drop year-like, epoch-like, and very large tokens
        url_nums = [
            n for n in url_nums
            if not is_year_token(n)
            and not is_timestamp_token(n)
            and (len(n) < 7 and int(float(n)) < 1_000_000)
        ]


        # prefer numbers that appear after chapter/chap/read/page in the URL
        m_after = re.search(r"(?:chapter|chap|read|page)[^0-9]{0,6}(\d+(?:\.\d+)?)", full, re.IGNORECASE)
        if m_after:
            try:
                chap_num = float(m_after.group(1))
            except Exception:
                chap_num = None

                # --- reject obviously bogus chapter numbers (timestamps / huge IDs) ---
        if chap_num is not None:
            try:
                # treat as integer for threshold checks
                n = int(float(chap_num))
            except Exception:
                n = None

            # ignore year-like, epoch-like, or otherwise absurdly large numbers
            if n is not None:
                if 1900 <= n <= 2100:
                    # a year alone is not a chapter number (unless you want to allow it)
                    chap_num = None
                elif n >= 1_000_000:   # epoch-like or huge ID
                    chap_num = None
                elif n >= 100_000:     # very large, unlikely to be a real chapter
                    chap_num = None

        if chap_num is None:
            continue


        # --- end improved extraction ---


        # Strict ID check: require the page's numeric manga id to appear in candidate URL
        if expected_id and expected_id not in full:
            # allow only if anchor text clearly mentions the title (first 3 words)
            title_words = [w.lower() for w in (title or "").split()[:3]]
            if not any(w for w in title_words if w and w in text.lower()):
                continue

        # small boost if anchor text contains title words
        boost = 0.1 if title and any(w.lower() in text.lower() for w in title.split()[:3]) else 0.0

        candidates.append({
            "url": normalize_url(full),
            "text": text,
            "score": chap_num + boost
        })

    # debug output (only inside function so variables exist)
    if debug:
        print("DEBUG canonical_page_url:", canonical_page_url)
        print("DEBUG expected_id:", expected_id)
        print("DEBUG candidate count:", len(candidates))
        for c in sorted(candidates, key=lambda x: x['score'], reverse=True)[:12]:
            print("DEBUG CAND:", c['score'], c['url'], repr(c['text'][:80]))

    if not candidates:
        return None

    best = max(candidates, key=lambda x: x["score"])

    # follow redirects for the chosen chapter URL and normalize
    try:
        r = fetch_url(url, timeout=15, allow_cloudscraper=True, debug=True)
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
            latest = find_latest_chapter(page, title, debug=True)
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

#!/usr/bin/env python3
"""Refresh the homepage news list from public scam-alert sources.

Primary source: 內政部警政署 165 全民防騙網 public article API
  https://165.npa.gov.tw/api/article/list/9  (涉詐資訊公告)
  https://165.npa.gov.tw/api/article/list/1  (新聞快訊)
Each item links to https://165.npa.gov.tw/article/<category>/<id>.

Fallback: 中央社 public RSS (social, local, life), titles that mention
scams only. Original article URLs are kept. No API key is required.

The script rewrites site/data/news.json and the marked block in
site/index.html. If the item list is unchanged, files are left as they are.
"""

from __future__ import annotations

import email.utils
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "site" / "index.html"
DATA_PATH = ROOT / "site" / "data" / "news.json"

TPE = timezone(timedelta(hours=8))
MAX_ITEMS = 6
FRESH_DAYS = 60
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 165 article categories that are public awareness posts, not forms.
NPA_LISTS = (
    ("9", "https://165.npa.gov.tw/api/article/list/9"),
    ("1", "https://165.npa.gov.tw/api/article/list/1"),
)
NPA_HOME = "https://165.npa.gov.tw/"
NPA_NAME = "內政部警政署 165 全民防騙網"
NPA_LABEL = "165 官方"

CNA_FEEDS = (
    "https://feeds.feedburner.com/rsscna/social",
    "https://feeds.feedburner.com/rsscna/local",
    "https://feeds.feedburner.com/rsscna/lifehealth",
)
CNA_HOME = "https://www.cna.com.tw/"
CNA_NAME = "中央社"
CNA_LABEL = "中央社"
SCAM_WORDS = (
    "詐騙",
    "詐欺",
    "阻詐",
    "防詐",
    "反詐",
    "被騙",
    "遭騙",
    "騙款",
    "釣魚",
    "車手",
    "假投資",
    "假檢警",
    "一頁式",
)
# Headlines about expense fraud or corruption are not scam-awareness alerts.
CNA_SKIP = ("助理費", "詐領")

NEWS_RE = re.compile(r"<!-- NEWS:START -->.*?<!-- NEWS:END -->", re.DOTALL)


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/xml, text/xml, */*",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
    assert last_error is not None
    raise last_error


def clean_title(value: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return re.sub(r"\s+", " ", text).strip()


def display_date(moment: datetime) -> str:
    local = moment.astimezone(TPE)
    return f"{local.year}年{local.month}月{local.day}日"


def make_item(title: str, moment: datetime, url: str, source: str) -> dict:
    local = moment.astimezone(TPE)
    return {
        "title": title,
        "date": local.date().isoformat(),
        "displayDate": display_date(local),
        "url": url,
        "source": source,
        "_sort": local.isoformat(),
    }


def fetch_165() -> list[dict]:
    items: list[dict] = []
    errors: list[str] = []
    for category, url in NPA_LISTS:
        try:
            payload = json.loads(fetch_bytes(url).decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeError) as error:
            errors.append(f"{url}: {error}")
            continue
        if not isinstance(payload, list):
            errors.append(f"{url}: expected a list")
            continue
        for row in payload:
            if not isinstance(row, dict):
                continue
            title = clean_title(str(row.get("title") or ""))
            raw_id = row.get("id")
            raw_date = row.get("publishDate")
            if not title or raw_id is None or not raw_date:
                continue
            try:
                article_id = int(raw_id)
                published = datetime.fromisoformat(str(raw_date))
            except (TypeError, ValueError):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=TPE)
            link = f"https://165.npa.gov.tw/article/{category}/{article_id}"
            items.append(make_item(title, published, link, NPA_LABEL))
    if errors and not items:
        raise RuntimeError("; ".join(errors))
    for message in errors:
        print(f"warning: {message}", file=sys.stderr)
    return items


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(node: ET.Element, name: str) -> str:
    for child in node:
        if local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def fetch_cna() -> list[dict]:
    items: list[dict] = []
    errors: list[str] = []
    for url in CNA_FEEDS:
        try:
            root = ET.fromstring(fetch_bytes(url))
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError, UnicodeError) as error:
            errors.append(f"{url}: {error}")
            continue
        for node in root.iter():
            if local_name(node.tag) != "item":
                continue
            title = clean_title(child_text(node, "title"))
            link = child_text(node, "link").strip()
            published_raw = child_text(node, "pubDate")
            if not title or not any(word in title for word in SCAM_WORDS):
                continue
            if any(word in title for word in CNA_SKIP):
                continue
            if not link.startswith("https://www.cna.com.tw/") and not link.startswith("https://cna.com.tw/"):
                continue
            try:
                published = email.utils.parsedate_to_datetime(published_raw)
            except (TypeError, ValueError, IndexError):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=TPE)
            items.append(make_item(title, published, link, CNA_LABEL))
    if errors and not items:
        raise RuntimeError("; ".join(errors))
    for message in errors:
        print(f"warning: {message}", file=sys.stderr)
    return items


def newest_age_days(items: list[dict]) -> float | None:
    if not items:
        return None
    newest = max(datetime.fromisoformat(item["_sort"]) for item in items)
    return (datetime.now(TPE) - newest).total_seconds() / 86400


def select_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for item in sorted(items, key=lambda row: row["_sort"], reverse=True):
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        unique.append(item)
    return unique[:MAX_ITEMS]


def choose_source() -> tuple[list[dict], str, str]:
    """Return items, source name, and source home URL."""
    try:
        npa_items = fetch_165()
    except Exception as error:  # noqa: BLE001 - try the public RSS fallback
        print(f"warning: 165 source failed: {error}", file=sys.stderr)
        npa_items = []

    npa_age = newest_age_days(npa_items)
    if npa_items and npa_age is not None and npa_age <= FRESH_DAYS:
        return select_items(npa_items), NPA_NAME, NPA_HOME

    if npa_items:
        print(
            f"warning: newest 165 item is {npa_age:.0f} days old; trying 中央社 RSS",
            file=sys.stderr,
        )

    try:
        cna_items = fetch_cna()
    except Exception as error:  # noqa: BLE001 - report after both sources fail
        print(f"warning: 中央社 source failed: {error}", file=sys.stderr)
        cna_items = []

    if cna_items:
        return select_items(cna_items), CNA_NAME, CNA_HOME
    if npa_items:
        return select_items(npa_items), NPA_NAME, NPA_HOME
    raise RuntimeError("no scam alerts from 165 or 中央社")


def signature(items: list[dict]) -> list[tuple[str, str, str, str]]:
    return [(item["date"], item["url"], item["title"], item["source"]) for item in items]


def load_previous() -> list[tuple[str, str, str, str]] | None:
    if not DATA_PATH.exists():
        return None
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        rows = data["items"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    result = []
    for row in rows:
        try:
            result.append((row["date"], row["url"], row["title"], row["source"]))
        except (KeyError, TypeError):
            return None
    return result


def render_news(items: list[dict], updated: datetime, source_name: str, source_url: str) -> str:
    lines = [
        "<!-- NEWS:START -->",
        f'<p class="updated">這份清單更新時間：{escape(display_date(updated))}</p>',
        '<ul class="news">',
    ]
    for item in items:
        lines.extend(
            [
                "  <li>",
                f'    <a href="{escape(item["url"], quote=True)}">',
                f'      <span class="date">{escape(item["displayDate"])}</span>',
                f'      <span class="headline">{escape(item["title"])}</span>',
                f'      <span class="from">出處：{escape(item["source"])}</span>',
                '      <span class="go">看原文</span>',
                "    </a>",
                "  </li>",
            ]
        )
    lines.extend(
        [
            "</ul>",
            (
                '<p class="source-note">資料來自'
                f'<a href="{escape(source_url, quote=True)}">{escape(source_name)}</a>'
                "。點進去看原文和日期。</p>"
            ),
            "<!-- NEWS:END -->",
        ]
    )
    return "\n".join(lines)


def write_outputs(items: list[dict], source_name: str, source_url: str) -> None:
    updated = datetime.now(TPE).replace(microsecond=0)
    public_items = []
    for item in items:
        public_items.append({key: value for key, value in item.items() if key != "_sort"})
    payload = {
        "updated": updated.isoformat(),
        "sourceName": source_name,
        "sourceUrl": source_url,
        "items": public_items,
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    html = INDEX_PATH.read_text(encoding="utf-8")
    block = render_news(items, updated, source_name, source_url)
    updated_html, count = NEWS_RE.subn(block, html, count=1)
    if count != 1:
        raise RuntimeError("site/index.html is missing the NEWS markers")
    INDEX_PATH.write_text(updated_html, encoding="utf-8")


def main() -> int:
    items, source_name, source_url = choose_source()
    if not items:
        print("error: source returned no items", file=sys.stderr)
        return 1
    if load_previous() == signature(items):
        print(f"No change in alerts ({len(items)} items, {source_name})")
        return 0
    write_outputs(items, source_name, source_url)
    print(f"Updated {len(items)} items from {source_name}")
    for item in items:
        print(f"- {item['displayDate']} {item['title']}")
        print(f"  {item['url']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - top-level CLI error
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)

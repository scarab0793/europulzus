#!/usr/bin/env python3
"""Offline-only marketing preview. Never publishes or edits site content."""
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

class NewsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "news-data" and dict(attrs).get("type") == "application/json":
            self.inside = True
    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False
    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)

def read_news(path):
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        parser = NewsParser()
        parser.feed(path.read_text(encoding="utf-8"))
        if not parser.parts:
            raise ValueError("No embedded news-data JSON found")
        data = json.loads("".join(parser.parts))
    if not isinstance(data, list):
        raise ValueError("Expected a news array")
    return data

def normalized_url(url):
    s = urlsplit(url)
    return urlunsplit((s.scheme.lower(), s.netloc.lower(), s.path.rstrip("/"), s.query, ""))

def key_for(item):
    title = re.sub(r"\s+", " ", str(item.get("t", "")).casefold()).strip()
    value = "|".join((str(item.get("d", "")), str(item.get("c", "")), title, normalized_url(str(item.get("u", "")))))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]

def candidate(item, today, max_age_days):
    try:
        published = date.fromisoformat(str(item.get("d", ""))[:10])
    except ValueError:
        return False, "invalid_date"
    if not 0 <= (today - published).days <= max_age_days:
        return False, "stale_or_future"
    if not item.get("t") or not item.get("src"):
        return False, "missing_title_or_source"
    u = urlsplit(str(item.get("u", "")))
    if u.scheme != "https" or not u.netloc:
        return False, "invalid_source_url"
    domain = u.netloc.lower().removeprefix("www.")
    if domain == "tradingeconomics.com":
        return False, "indicator_link_needs_verification"
    if domain in {"bloomberg.com", "cnbc.com"}:
        return False, "source_needs_manual_review"
    return True, "preview_only"

def build_preview(item):
    title = re.sub(r"\s+", " ", str(item.get("en") or item.get("t")).strip())
    title = title[:190] + ("…" if len(title) > 190 else "")
    return {
        "key": key_for(item), "date": item["d"], "country": item.get("c"),
        "source": item.get("src"), "source_url": item.get("u"),
        "text": title + "\n\nMore European economic updates: https://europulses.com/?utm_source=telegram&utm_medium=social&utm_campaign=organic_daily",
        "status": "PREVIEW_ONLY_NOT_FACT_CHECKED"
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="index.html")
    parser.add_argument("--output", default="marketing-preview.json")
    parser.add_argument("--max-age-days", type=int, default=2)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--today", default=None)
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    news = read_news(args.input)
    seen, selected, skipped = set(), [], {}
    for item in sorted(news, key=lambda x: str(x.get("d", "")) if isinstance(x, dict) else "", reverse=True):
        if not isinstance(item, dict):
            reason = "invalid_item"
        else:
            key = key_for(item)
            if key in seen:
                reason = "duplicate"
            else:
                seen.add(key)
                ok, reason = candidate(item, today, args.max_age_days)
                if ok:
                    if len(selected) < args.limit:
                        selected.append(build_preview(item))
                    continue
        skipped[reason] = skipped.get(reason, 0) + 1
    result = {
        "mode": "DRY_RUN", "publish_enabled": False, "checked_on": today.isoformat(),
        "input_items": len(news), "preview_count": len(selected), "skipped": skipped,
        "warning": "Not independently fact-checked. No posts sent.", "previews": selected
    }
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"DRY RUN: {len(news)} items; {len(selected)} previews; NO POSTS SENT.")

if __name__ == "__main__":
    main()

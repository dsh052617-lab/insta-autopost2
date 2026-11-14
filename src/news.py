"""신뢰할 수 있는 피드에서만 기사 후보를 모으고, 본문을 원문 페이지에서 직접 가져온다."""
from __future__ import annotations

import calendar
import html
import re
import time
from urllib.parse import urlparse

import feedparser
import requests
import trafilatura

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TAG_RE = re.compile(r"<[^>]+>")
# 다른 매체에 실린 통신사 기사 감지: (서울=연합뉴스) / [세종=뉴시스] / (서울=뉴스1)
WIRE_RE = re.compile(r"[\(\[][^\)\]=]{1,12}=(연합뉴스|뉴시스|뉴스1)[\)\]]")


def wire_origin(text: str) -> str | None:
    m = WIRE_RE.search(text[:600])
    return m.group(1) if m else None


def _clean(text: str, limit: int) -> str:
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _norm_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", title.lower())[:40]


def _base_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    parts = host.split(".")
    # yna.co.kr / bbc.co.uk 같은 2단계 국가 도메인 처리
    if len(parts) >= 3 and parts[-2] in {"co", "or", "go", "ac", "ne", "re", "pe", "com", "gov", "org", "net", "edu", "mil"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def trusted_domains(cfg: dict) -> set[str]:
    return set(cfg["sources"])


def is_trusted(url: str, domains: set[str]) -> bool:
    return _base_domain(url) in domains


def source_info(cfg: dict, url: str) -> dict:
    """도메인으로 출처 이름과 구분(official/press)을 찾는다."""
    return cfg["sources"].get(_base_domain(url), {"name": urlparse(url).netloc, "tier": "press"})


def collect(cfg: dict, feeds: list[dict], lookback_days: int, exclude_urls: set[str],
            per_feed: int = 15) -> list[dict]:
    domains = trusted_domains(cfg)
    cutoff = time.time() - lookback_days * 86400
    items, seen = [], set()
    for feed in feeds:
        try:
            resp = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=20)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception as e:  # 피드 하나가 죽어도 나머지는 계속
            print(f"⚠️  피드 실패: {feed['url']} ({e})")
            continue
        keywords = [k.lower() for k in feed.get("keywords", [])]
        count = 0
        for entry in parsed.entries:
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            ts = calendar.timegm(stamp) if stamp else time.time()
            title = _clean(entry.get("title", ""), 200)
            link = entry.get("link", "")
            summary = _clean(entry.get("summary", ""), 300)
            if ts < cutoff or not title or not link or link in exclude_urls:
                continue
            if not is_trusted(link, domains):
                continue
            if keywords and not any(k in (title + " " + summary).lower() for k in keywords):
                continue
            key = _norm_title(title)
            if key in seen:
                continue
            seen.add(key)
            info = source_info(cfg, link)
            items.append({"title": title, "url": link, "source": info["name"], "tier": info["tier"],
                          "summary": summary, "ts": ts,
                          "published": time.strftime("%Y-%m-%d", time.gmtime(ts))})
            count += 1
            if count >= per_feed:
                break
        print(f"✓ {feed['url'][:60]}: {count}건")
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:90]


def fetch_article(cfg: dict, item: dict, max_chars: int = 8000) -> dict | None:
    """원문 페이지에서 본문을 가져온다. 신뢰 도메인이 아니거나 본문이 짧으면 None."""
    domains = trusted_domains(cfg)
    min_chars = cfg["news"]["min_article_chars"]
    if not is_trusted(item["url"], domains):
        print(f"⚠️  신뢰 목록 밖 → 제외: {item['url']}")
        return None
    try:
        resp = requests.get(item["url"], headers={"User-Agent": UA}, timeout=25)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️  원문 접속 실패 → 제외: {item['url']} ({e})")
        return None
    if not is_trusted(resp.url, domains):
        print(f"⚠️  신뢰 목록 밖으로 이동 → 제외: {resp.url}")
        return None
    text = trafilatura.extract(resp.text, favor_precision=True, include_comments=False) or ""
    if len(text) < min_chars:
        print(f"⚠️  본문 부족({len(text)}자) → 제외: {item['url']}")
        return None
    meta = trafilatura.extract_metadata(resp.text)
    info = source_info(cfg, resp.url)
    return {"title": item.get("title") or (meta.title if meta and meta.title else resp.url),
            "published": item.get("published") or (meta.date if meta and meta.date else ""),
            **{k: v for k, v in item.items() if k not in ("title", "published")},
            "source": info["name"], "tier": info["tier"], "url": resp.url, "text": text[:max_chars],
            "origin": wire_origin(text) or info["name"]}

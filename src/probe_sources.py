"""출처 접속 점검: 매체·기관별로 '자동 실행(GitHub)에서 기사 본문을 가져올 수 있는지' 확인한다.
결과는 data/source_probe.md 에 저장 (python src/probe_sources.py)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news  # noqa: E402
from common import ROOT, load_config  # noqa: E402

FEEDS = [  # (이름, RSS 후보들) — 첫 번째로 열리는 피드의 최신 기사 1~2개로 본문 가져오기를 시험
    ("한국경제", ["https://www.hankyung.com/feed/economy", "https://www.hankyung.com/feed/finance"]),
    ("매일경제", ["https://www.mk.co.kr/rss/30100041/", "https://www.mk.co.kr/rss/50200011/"]),
    ("한국은행", ["https://www.bok.or.kr/portal/bbs/P0000559/news.rss?menuNo=200690",
              "https://www.bok.or.kr/portal/bbs/P0000093/news.rss?menuNo=200789"]),
    ("금융위원회", ["https://www.fsc.go.kr/about/fsc_bbs_rss/?fid=0111", "http://www.fsc.go.kr/about/fsc_bbs_rss/?fid=0111"]),
    ("금융감독원", ["https://www.fss.or.kr/fss/bbs/B0000188/rss.do?mi=1021"]),
    ("정책브리핑(정부 보도자료)", ["https://www.korea.kr/rss/pressrelease.xml", "https://www.korea.kr/rss/policy.xml"]),
    ("기획재정부", ["https://www.moef.go.kr/com/detailRssTagService.do?bbsId=MOSFBBS_000000000028"]),
    ("연합뉴스", ["https://www.yna.co.kr/rss/economy.xml"]),
    ("뉴스1", ["https://www.news1.kr/rss/economy"]),
    ("뉴시스", ["https://www.newsis.com/RSS/economy.xml"]),
    ("서울경제", ["https://www.sedaily.com/rss/economy"]),
    ("머니투데이", ["https://rss.mt.co.kr/mt_news.xml"]),
    ("이데일리", ["http://rss.edaily.co.kr/edaily_news.xml"]),
    ("파이낸셜뉴스", ["https://www.fnnews.com/rss/r20/fn_realnews_all.xml"]),
    ("헤럴드경제", ["https://biz.heraldcorp.com/rss/google/economy"]),
    ("아시아경제", ["https://www.asiae.co.kr/rss/economy.htm"]),
    ("조선일보", ["https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"]),
    ("동아일보", ["https://rss.donga.com/economy.xml"]),
    ("한겨레", ["https://www.hani.co.kr/rss/economy/"]),
    ("경향신문", ["https://www.khan.co.kr/rss/rssdata/economy_news.xml"]),
]
URLS = [  # 직접 시험할 기사 주소
    ("뉴스1 (11/15 불법사금융)", "https://www.news1.kr/finance/general-finance/6354296"),
    ("아시아경제 (11/15 불법사금융)", "https://view.asiae.co.kr/article/2026111511531056567"),
    ("이투데이 (11/15 불법사금융)", "https://www.etoday.co.kr/news/view/2648258"),
    ("Artificial Analysis 모델 비교", "https://artificialanalysis.ai/models"),
    ("Artificial Analysis 지능 지수", "https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index"),
    ("Artificial Analysis GPQA", "https://artificialanalysis.ai/evaluations/gpqa-diamond"),
    ("Artificial Analysis HLE", "https://artificialanalysis.ai/evaluations/humanitys-last-exam"),
    ("Epoch AI 벤치마크", "https://epoch.ai/benchmarks"),
    ("Epoch AI SWE-bench", "https://epoch.ai/benchmarks/swe-bench-verified"),
    ("LMArena 순위", "https://lmarena.ai/leaderboard"),
    ("Vals AI SWE-bench", "https://www.vals.ai/benchmarks/swebench"),
    ("Stanford AI Index 2026", "https://hai.stanford.edu/ai-index/2026-ai-index-report"),
    ("SWE-bench 공식 순위", "https://www.swebench.com/"),
]


def try_article(cfg, url):
    from urllib.parse import urlparse
    host = urlparse(url).netloc.removeprefix("www.")
    cfg = {**cfg, "sources": {**cfg["sources"], host: cfg["sources"].get(host) or {"name": host, "tier": "press"}}}
    a = news.fetch_article(cfg, {"url": url, "title": "", "published": ""})
    return (f"✅ 본문 {len(a['text'])}자" if a else "❌ 본문 못 가져옴")


def main():
    cfg = load_config()
    lines = [f"# 출처 접속 점검 ({dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC, GitHub 실행 환경)", "",
             "| 매체·기관 | 피드 | 기사 본문 |", "|---|---|---|"]
    for name, cands in FEEDS:
        feed_note, art_note = "❌ 피드 없음", "-"
        for f in cands:
            try:
                r = requests.get(f, headers={"User-Agent": news.UA}, timeout=20)
                d = feedparser.parse(r.content)
            except Exception as e:
                feed_note = f"❌ {type(e).__name__}"
                continue
            if r.status_code == 200 and d.entries:
                feed_note = f"✅ {len(d.entries)}건"
                notes = [try_article(cfg, e.get("link", "")) for e in d.entries[:2] if e.get("link")]
                art_note = " / ".join(notes) or "-"
                break
            feed_note = f"❌ {r.status_code}"
        lines.append(f"| {name} | {feed_note} | {art_note} |")
        print(lines[-1], flush=True)
    lines += ["", "| 기사 | 결과 |", "|---|---|"]
    for name, u in URLS:
        lines.append(f"| {name} | {try_article(cfg, u)} |")
        print(lines[-1], flush=True)
    out = ROOT / "data" / "source_probe.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

"""기사 주소 찾기: 검색어로 포털 뉴스 검색 결과에서 신뢰 출처(config.yaml sources) 기사 주소만 골라 저장.
python src/find_news.py "검색어1" "검색어2"  →  preview/found.txt"""
from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9"}


def trusted(cfg: dict, url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    for dom in cfg.get("sources", {}):
        if host == dom or host.endswith("." + dom):
            return dom
    return ""


def search(q: str) -> list[str]:
    urls = []
    for base in ("https://search.naver.com/search.naver?where=news&sort=1&query=",
                 "https://search.daum.net/search?w=news&sort=recency&q="):
        try:
            r = requests.get(base + urllib.parse.quote(q), headers=UA, timeout=20)
            urls += re.findall(r'href="(https?://[^"]+)"', r.text)
        except requests.RequestException as e:
            urls.append(f"ERROR {e}")
    return urls


def main() -> None:
    cfg = load_config()
    out = []
    for q in sys.argv[1:]:
        out.append(f"## {q}")
        seen = set()
        for u in search(q):
            u = u.replace("&amp;", "&")
            if u in seen or not trusted(cfg, u):
                continue
            if re.search(r"/(search|section|list|main)\b|\.(css|js|png|jpg)", u):
                continue
            seen.add(u)
            out.append(f"{trusted(cfg, u)}  {u}")
    p = ROOT / "preview" / "found.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()

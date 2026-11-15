"""출처 본문 미리 보기: 검증 프로그램이 실제로 읽는 본문을 그대로 저장한다 (원고의 근거 구절을 맞출 때 사용).
python src/fetch_text.py URL [URL ...]  →  preview/fetched/<번호>.txt"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news  # noqa: E402
from common import ROOT, load_config  # noqa: E402


def main() -> None:
    cfg = load_config()
    out = ROOT / "preview" / "fetched"
    out.mkdir(parents=True, exist_ok=True)
    for i, u in enumerate(sys.argv[1:], 1):
        a = news.fetch_article(cfg, {"url": u}, max_chars=60000)
        body = (f"URL: {u}\nSOURCE: {a['source']} ({a['tier']})\nPUBLISHED: {a.get('published', '')}\n\n{a['text']}"
                if a else f"URL: {u}\n(본문을 가져오지 못함 — 신뢰 목록 밖이거나 차단·본문 부족)")
        (out / f"{i:02d}.txt").write_text(body, encoding="utf-8")
        print(f"{i:02d}: {'OK' if a else 'FAIL'} {u}")


if __name__ == "__main__":
    main()

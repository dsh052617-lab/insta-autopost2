"""내 주제로 카드뉴스 만들기 — 자동 업로드와 같은 디자인·출처 규칙·검증을 그대로 사용.

요청 방법
  1) GitHub 저장소에서 새 이슈 만들기 → 제목을 `주제: 청년도약계좌 바뀐 점` 처럼 쓰기
     (본문에 원하는 관점이나 참고할 신뢰 출처 링크를 적어도 돼요)
  2) 또는 Actions → '5. 내 주제로 만들기' → Run workflow 에서 주제 입력

  python src/custom.py --topic "청년도약계좌 바뀐 점" [--issue 12] [--local]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import news  # noqa: E402
import verify  # noqa: E402
import writer  # noqa: E402
from common import DRAFTS, ROOT, git_commit_push, load_config, now  # noqa: E402
from draft import SOURCE_KEYS, issue_body, issue_title, render_version  # noqa: E402

URL_RE = re.compile(r"https?://[^\s)>\]]+")


def gather(cfg: dict, topic: str, extra: str) -> tuple[list[dict], dict]:
    """사용자가 준 신뢰 출처 링크 + 신뢰 출처 안 웹 검색으로 원문을 모은다."""
    domains = sorted(news.trusted_domains(cfg))
    given = [u for u in URL_RE.findall(extra) if news.is_trusted(u, set(domains))]
    articles: list[dict] = []
    for u in given:
        a = news.fetch_article(cfg, {"url": u})
        if a:
            articles.append(a)
    plan = {"category": "", "angle": ""}
    avoid: list[str] = []
    for _ in range(2):
        if articles and not verify.source_rule(articles):
            break
        print("   신뢰 출처 안에서 검색 중…")
        found = writer.research(cfg, f"{topic}\n{extra}".strip(), domains, avoid)
        plan.update({k: found.get(k, "") for k in ("category", "angle")})
        for u in found.get("urls", []):
            if u in avoid or any(a["url"] == u for a in articles):
                continue
            avoid.append(u)
            a = news.fetch_article(cfg, {"url": u})
            if a:
                articles.append(a)
                print(f"   - [{a['tier']}] {a['source']}: {a['title'][:50]}")
    # 같은 출처가 중복되면 앞의 것만, 최대 개수 제한
    return articles[: cfg["news"]["max_articles_per_post"] + 1], plan


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--detail", default="", help="원하는 관점이나 참고 링크")
    ap.add_argument("--issue", type=int, default=0, help="요청 이슈 번호 (그 이슈를 초안으로 바꿈)")
    ap.add_argument("--category", default="", choices=["", "ai", "economy"])
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    topic = args.topic.strip()
    print(f"▶ 내 주제: {topic}")

    gh = None
    if not args.local:
        import github_api as gh
        gh.ensure_labels()
        if args.issue:
            gh.comment(args.issue, "🔎 신뢰 출처에서 자료를 찾고 카드뉴스를 만드는 중이에요 (3~5분).")

    print("① 신뢰 출처 자료 모으기")
    articles, plan = gather(cfg, topic, args.detail)
    problem = "신뢰 출처에서 원문을 가져온 자료가 없어요." if not articles else verify.source_rule(articles)
    if problem:
        msg = (f"❌ 이 주제는 출처 조건을 만족하는 자료를 찾지 못해 만들지 않았어요.\n- {problem}\n\n"
               "주제를 조금 더 구체적으로 적거나, 본문에 신뢰 출처(정부·한국은행·주요 언론) 링크를 붙여 다시 요청해 주세요.")
        print(msg)
        if gh and args.issue:
            gh.comment(args.issue, msg)
        sys.exit(1)

    category = args.category or plan.get("category") or "economy"
    if category not in cfg["topics"]:
        category = "economy"
    angle = (f"운영자가 요청한 주제: {topic}. {args.detail} "
             f"{plan.get('angle', '')} 독자(일반 국민)에게 실제로 도움이 되도록.").strip()

    print("② 카드뉴스 쓰기 + 출처 검증")
    post, result = writer.write_verified(cfg, category, articles, angle)
    print("   " + ("✅ 검증 통과" if result["passed"] else f"❌ 검증 실패: {result['problems']}"))

    stamp = now(cfg).strftime("%Y%m%d-%H%M")
    draft_dir = (ROOT / "preview" / f"custom-{stamp}") if args.local else (DRAFTS / f"custom-{stamp}")
    draft_dir.mkdir(parents=True, exist_ok=True)
    data = {"date": now(cfg).date().isoformat(), "topic": category, "version": 1, "post": post,
            "custom": True, "request": topic,
            "sources": [{k: a[k] for k in SOURCE_KEYS} for a in articles],
            "story": {"reason": "운영자가 요청한 주제", "angle": angle},
            "verification": result}

    print("③ 이미지 만들기")
    paths = render_version(cfg, data, draft_dir)
    (draft_dir / "post.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.local:
        print(f"✅ 미리보기 완료: {draft_dir}")
        return

    git_commit_push(f"custom draft: {topic[:40]}", [draft_dir])
    title, body = issue_title(cfg, data), issue_body(cfg, data, paths, draft_dir)
    if args.issue:  # 요청한 이슈를 그대로 초안 이슈로 바꿈
        gh.update_issue(args.issue, title=title, body=body)
        gh.add_labels(args.issue, ["draft"])
        gh.comment(args.issue, "🆕 초안을 본문에 올렸어요. 확인하고 `승인`하면 바로 게시돼요.")
    else:
        issue = gh.create_issue(title, body, ["draft"])
        print(f"✅ 검토 요청 이슈: {issue['html_url']}")


if __name__ == "__main__":
    main()

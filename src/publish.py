"""승인된 초안을 인스타그램에 게시.

  python src/publish.py              # 오늘 게시 예정인 승인된 초안을 예정 시각에 게시
  python src/publish.py --issue 12   # 특정 이슈를 지금 바로 게시
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import github_api as gh  # noqa: E402
import instagram  # noqa: E402
from common import (ROOT, append_history_and_push, load_config, now, post_datetime,  # noqa: E402
                    raw_url)
from draft import build_caption  # noqa: E402


def publish_issue(cfg: dict, issue: dict) -> str:
    issue = gh.get_issue(issue["number"])  # 최신 상태로 다시 확인 (중복 게시 방지)
    if issue["state"] != "open" or "published" in gh.label_names(issue):
        print(f"#{issue['number']}은 이미 처리됐어요.")
        return ""
    marker = gh.read_marker(issue)
    if not marker or not marker.get("dir"):
        raise RuntimeError("이 이슈에서 초안 정보를 찾지 못했어요 (본문 맨 아래 숨김 표시가 지워졌을 수 있어요).")
    draft_dir = ROOT / marker["dir"]
    post_file = draft_dir / "post.json"
    if not post_file.exists():
        raise RuntimeError(f"초안 파일 {marker['dir']}/post.json 이 저장소에 없어요.")
    data = json.loads(post_file.read_text(encoding="utf-8"))
    if not data.get("verification", {}).get("passed"):
        gh.comment(issue["number"], "❌ 출처 검증을 통과하지 못한 초안이라 게시하지 않았어요.")
        raise RuntimeError("출처 검증 미통과 초안은 게시할 수 없어요.")
    images = sorted((draft_dir / f"v{data['version']}").glob("*.jpg"))
    if len(images) < 2:
        raise RuntimeError(f"카드 이미지가 {len(images)}장뿐이에요. `수정: 다시 그려줘`로 새 버전을 만들어 주세요.")
    urls = [raw_url(p) for p in images]
    for u in urls[:1]:  # 인스타가 가져갈 이미지 주소가 실제로 열리는지 먼저 확인
        try:
            ok = requests.head(u, timeout=20, allow_redirects=True).status_code == 200
        except requests.RequestException:
            ok = False
        if not ok:
            raise RuntimeError(f"카드 이미지 주소가 열리지 않아요: {u}\n저장소가 공개(Public)인지 확인해 주세요.")
    caption = build_caption(data["post"], data["sources"])

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("IG_ACCESS_TOKEN 시크릿이 비어 있어요. Meta에서 발급한 토큰을 GitHub Secrets에 넣어주세요.")
    user_id = os.environ.get("IG_USER_ID", "").strip() or instagram.my_user_id(token)
    result = instagram.publish_carousel(
        user_id, token, urls, caption,
        ai_label=cfg["instagram"].get("ai_label", True))

    # 게시 성공 직후 가장 먼저 '게시됨' 표시 → 이후 단계가 실패해도 예비 실행이 다시 올리는 일(중복 게시)이 없게
    link = result["permalink"] or "(링크를 가져오지 못했어요 — 인스타 앱에서 확인해주세요)"
    for step in (lambda: gh.add_labels(issue["number"], ["published"]),
                 lambda: gh.comment(issue["number"], f"🎉 인스타에 게시했어요!\n{link}"),
                 lambda: gh.update_issue(issue["number"], state="closed")):
        try:
            step()
        except Exception as e:
            print(f"⚠️  게시 후 이슈 정리 실패(게시는 완료): {e}")

    entry = {"date": data["date"], "topic": data["topic"], "kind": data.get("kind", "news"),
             "category": data.get("story", {}).get("category", ""),
             "title": data["post"]["cover_title"].replace("\\n", " ").replace("\n", " "),
             "urls": [s["url"] for s in data["sources"]],
             "media_id": result["media_id"], "permalink": result["permalink"]}
    try:  # 다른 작업(내 주제·자동)과 동시에 기록해도 충돌 없이 합쳐서 저장
        append_history_and_push(entry, f"published: {marker['dir']}")
    except Exception as e:
        print(f"⚠️  게시 기록 저장 실패(게시는 완료): {e}")
        gh.comment(issue["number"], f"ℹ️ 게시는 됐지만 기록 파일 저장에 실패했어요. 다음 주제 고를 때 이 글을 모를 수 있어요.\n`{str(e)[:200]}`")
    return link


def publish_or_report(cfg: dict, issue: dict) -> str:
    """게시하다 실패하면 이유를 이슈 댓글로 남긴다 (폰 알림으로 바로 확인 가능)."""
    try:
        return publish_issue(cfg, issue)
    except Exception as e:
        try:
            gh.comment(issue["number"], f"⚠️ 게시에 실패했어요.\n```\n{str(e)[:600]}\n```\n"
                                        f"실행 기록: {gh.run_link()}\n"
                                        "원인을 해결한 뒤 `지금 게시`라고 달면 다시 시도해요.")
        except Exception:
            pass
        e.reported = True
        raise


def close_stale_drafts(cfg: dict) -> None:
    """게시일이 지난 (내 주제 아닌) 초안은 정리한다."""
    today = now(cfg).date().isoformat()
    for issue in gh.open_drafts():
        m = gh.read_marker(issue) or {}
        if m and not m.get("custom") and m.get("date", today) < today:
            gh.comment(issue["number"], "게시일이 지나서 이 초안은 닫을게요. 필요하면 다시 열고 `지금 게시`라고 달아주세요.")
            gh.add_labels(issue["number"], ["skipped"])
            gh.update_issue(issue["number"], state="closed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int, default=0)
    args = ap.parse_args()
    cfg = load_config()

    if args.issue:
        print(publish_or_report(cfg, gh.get_issue(args.issue)))
        return

    close_stale_drafts(cfg)

    today = now(cfg).date()
    todays = []
    for i in gh.open_drafts():
        m = gh.read_marker(i) or {}
        if m.get("date") == today.isoformat() and not m.get("custom"):
            todays.append((post_datetime(cfg, today, m.get("topic")), i))
    todays.sort(key=lambda x: x[0])
    if not todays:
        print("오늘 게시 예정인 초안이 없어요.")
        return

    failed = False
    for target, issue in todays:
        wait = (target - now(cfg)).total_seconds()
        if wait > 40 * 60:  # 이 회차는 다음 실행이 맡음 (주제마다 게시 시각이 달라요)
            print(f"#{issue['number']}은 {target:%H:%M} 예정 — 이번 실행에서는 건너뜀")
            continue
        # GitHub 예약 실행은 몇 분씩 늦거나 이를 수 있어서, 이르면 예정 시각까지 기다린다
        if wait > 0:
            print(f"#{issue['number']} 예정 시각({target:%H:%M})까지 {int(wait // 60)}분 대기")
            time.sleep(wait)
        issue = gh.get_issue(issue["number"])  # 기다리는 동안 달린 승인 반영
        if issue["state"] != "open":
            continue
        if "approved" in gh.label_names(issue):
            try:
                print("게시:", publish_or_report(cfg, issue))
            except Exception as e:  # 한 건이 실패해도 다른 초안은 계속
                print(f"#{issue['number']} 게시 실패: {e}")
                failed = True
        else:
            # 예비 실행이 한 번 더 돌아도 같은 안내를 두 번 달지 않게
            if not any("⏸" in (c.get("body") or "") for c in gh.list_comments(issue["number"])):
                gh.comment(issue["number"],
                           "⏸ 승인 댓글이 없어서 예정 시각에 게시하지 않았어요.\n"
                           "지금이라도 올리려면 `지금 게시`, 건너뛰려면 `취소`라고 댓글 달아주세요.")
            print(f"#{issue['number']} 미승인 — 게시 안 함")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        if not getattr(e, "reported", False):
            gh.report_error(e, "인스타 게시")
        raise

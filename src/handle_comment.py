"""초안 이슈에 단 댓글(승인 / 수정: … / 지금 게시 / 취소)을 처리."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import github_api as gh  # noqa: E402
import writer  # noqa: E402
from common import ROOT, date_label, git_commit_push, load_config  # noqa: E402
from draft import SOURCE_KEYS, fetch_articles, issue_body, issue_title, render_version  # noqa: E402

BLOCKED = ("❌ 출처 검증을 통과하지 못한 초안이라 승인·게시할 수 없어요.\n"
           "`수정: 원문에 없는 내용은 빼줘`처럼 고치거나 `취소`해 주세요.")


def main() -> None:
    cfg = load_config()
    number = int(os.environ["ISSUE_NUMBER"])
    text = os.environ.get("COMMENT_BODY", "").strip()
    first = text.splitlines()[0].strip() if text else ""
    issue = gh.get_issue(number)
    marker = gh.read_marker(issue)
    if not marker:
        return
    draft_dir = ROOT / marker["dir"]
    data = json.loads((draft_dir / "post.json").read_text(encoding="utf-8"))
    passed = data.get("verification", {}).get("passed", False)
    when = f"{date_label(dt.date.fromisoformat(marker['date']))} {cfg['schedule']['post_time']}"

    if first.startswith("승인"):
        if not passed:
            gh.comment(number, BLOCKED)
            return
        if marker.get("custom"):  # 내 주제는 승인 즉시 게시
            from publish import publish_or_report as publish_issue
            gh.comment(number, "✅ 승인됐어요. 지금 인스타에 올릴게요…")
            publish_issue(cfg, issue)
            return
        gh.add_labels(number, ["approved"])
        gh.comment(number, f"✅ 승인됐어요. {when}에 인스타에 올라가요.")

    elif first.replace(" ", "").startswith("지금게시"):
        if not passed:
            gh.comment(number, BLOCKED)
            return
        from publish import publish_or_report as publish_issue
        gh.comment(number, "🚀 지금 게시할게요…")
        publish_issue(cfg, issue)

    elif first.startswith("취소"):
        gh.add_labels(number, ["skipped"])
        gh.update_issue(number, state="closed")
        gh.comment(number, "이번 회차는 건너뛸게요.")

    elif first.startswith("수정"):
        feedback = text[len("수정"):].lstrip(" :：").strip()
        if not feedback:
            gh.comment(number, "어떻게 고칠지 함께 적어주세요. 예: `수정: 제목을 덜 자극적으로`")
            return
        gh.comment(number, "✏️ 수정 중이에요. 원문을 다시 가져와 검증까지 하고 올릴게요 (1~2분).")
        articles = fetch_articles(cfg, data["sources"])
        if len(articles) < len(data["sources"]):
            gh.comment(number, "⚠️ 일부 원문을 다시 가져오지 못해, 확인된 원문만으로 검증해요.")
        post, result = writer.write_verified(cfg, data["topic"], articles, base=data["post"], feedback=feedback)
        data.update(post=post, verification=result, version=data["version"] + 1,
                    sources=[{k: a[k] for k in SOURCE_KEYS} for a in articles])
        paths = render_version(cfg, data, draft_dir)
        (draft_dir / "post.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        git_commit_push(f"revise: {marker['dir']} v{data['version']}", [draft_dir])
        gh.remove_label(number, "approved")  # 내용이 바뀌었으니 다시 승인 받기
        gh.update_issue(number, title=issue_title(cfg, data), body=issue_body(cfg, data, paths, draft_dir))
        if result["passed"]:
            gh.comment(number, f"🆕 새 버전(v{data['version']})이 출처 검증을 통과했어요. 괜찮으면 `승인`이라고 달아주세요.")
        else:
            gh.comment(number, f"⚠️ 새 버전(v{data['version']})도 출처 검증을 통과하지 못했어요. 본문의 문제 목록을 확인해주세요.")


if __name__ == "__main__":
    main()

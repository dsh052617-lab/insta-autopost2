"""GitHub 이슈로 초안 검토·승인을 주고받는다."""
from __future__ import annotations

import json
import os
import re
import time
import traceback

import requests

from common import repo

API = "https://api.github.com"
MARKER_RE = re.compile(r"<!-- insta-draft: (\{.*?\}) -->")

LABELS = {
    "draft": ("6E7781", "인스타 카드뉴스 초안"),
    "approved": ("1A7F37", "승인됨 — 예정 시각에 게시"),
    "published": ("8250DF", "인스타에 게시 완료"),
    "skipped": ("BF8700", "게시 안 함"),
    "error": ("D1242F", "자동 실행 중 오류"),
}


def _h() -> dict:
    return {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json"}


def _req(method: str, path: str, **kw):
    last = None
    for attempt in range(4):  # 일시 오류(5xx·속도 제한·네트워크)는 잠깐 쉬고 다시
        try:
            r = requests.request(method, f"{API}/repos/{repo()}{path}", headers=_h(), timeout=30, **kw)
        except requests.RequestException as e:
            last = str(e)
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code >= 500 or r.status_code == 429 or (
                r.status_code == 403 and "rate limit" in r.text.lower()):
            last = f"{r.status_code} {r.text[:200]}"
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub API {method} {path} 실패: {r.status_code} {r.text[:300]}")
        return r.json() if r.text else {}
    raise RuntimeError(f"GitHub API {method} {path} 실패(재시도 후): {last}")


def ensure_labels() -> None:
    existing = {l["name"] for l in _req("GET", "/labels", params={"per_page": 100})}
    for name, (color, desc) in LABELS.items():
        if name not in existing:
            _req("POST", "/labels", json={"name": name, "color": color, "description": desc})


def create_issue(title: str, body: str, labels: list[str]) -> dict:
    return _req("POST", "/issues", json={"title": title, "body": body, "labels": labels})


def get_issue(number: int) -> dict:
    return _req("GET", f"/issues/{number}")


def update_issue(number: int, **fields) -> dict:
    return _req("PATCH", f"/issues/{number}", json=fields)


def comment(number: int, text: str) -> None:
    _req("POST", f"/issues/{number}/comments", json={"body": text[:60000]})


def list_comments(number: int) -> list[dict]:
    return _req("GET", f"/issues/{number}/comments", params={"per_page": 100})


def _error_text(e: BaseException) -> str:
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    for key in ("ANTHROPIC_API_KEY", "IG_ACCESS_TOKEN", "GITHUB_TOKEN", "GH_PAT"):  # 혹시 모를 키 노출 방지
        val = os.environ.get(key)
        if val and len(val) > 8:
            tb = tb.replace(val, "***")
    return tb[-3000:]


def run_link() -> str:
    run = os.environ.get("GITHUB_RUN_ID")
    return f"https://github.com/{repo()}/actions/runs/{run}" if run else ""


def report_error(e: BaseException, where: str, issue_number: int = 0) -> None:
    """자동 실행이 실패하면 이유를 이슈로 남긴다 (폰 알림으로 바로 확인 가능). 이 함수 자체는 절대 실패하지 않게."""
    if not os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_ACTIONS") != "true":
        return
    body = (f"⚠️ **{where}** 중 오류가 났어요.\n\n```\n{_error_text(e)}\n```\n"
            f"실행 기록: {run_link()}\n\n이 내용을 그대로 캡처해서 물어보면 원인을 찾기 쉬워요.")
    try:
        if issue_number:
            comment(issue_number, body)
        else:
            ensure_labels()
            create_issue(f"[오류] {where}", body, ["error"])
    except Exception as inner:  # 알림 실패가 원래 오류를 가리지 않도록
        print(f"(오류 알림 실패: {inner})")


def add_labels(number: int, labels: list[str]) -> None:
    _req("POST", f"/issues/{number}/labels", json={"labels": labels})


def remove_label(number: int, label: str) -> None:
    try:
        _req("DELETE", f"/issues/{number}/labels/{label}")
    except RuntimeError:
        pass


def open_drafts() -> list[dict]:
    issues = _req("GET", "/issues", params={"labels": "draft", "state": "open", "per_page": 50})
    return [i for i in issues if "pull_request" not in i]


def recent_drafts() -> list[dict]:
    """열린 것과 닫힌 것(게시·취소) 모두 — 같은 날짜 초안을 다시 만들지 않기 위해."""
    issues = _req("GET", "/issues", params={"labels": "draft", "state": "all", "per_page": 30,
                                            "sort": "created", "direction": "desc"})
    return [i for i in issues if "pull_request" not in i]


def read_marker(issue: dict) -> dict | None:
    m = MARKER_RE.search(issue.get("body") or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def make_marker(data: dict) -> str:
    return f"<!-- insta-draft: {json.dumps(data, ensure_ascii=False)} -->"


def label_names(issue: dict) -> set[str]:
    return {l["name"] for l in issue.get("labels", [])}


def pending_posts(root) -> list[dict]:
    """아직 게시 전인 초안(자동·내 주제 모두)의 제목·출처·분야 — 서로 같은 이야기를 다루지 않게 하는 데 쓴다."""
    out = []
    for issue in open_drafts():
        m = read_marker(issue) or {}
        f = root / m.get("dir", "") / "post.json"
        if not m.get("dir") or not f.exists():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        out.append({"number": issue["number"], "date": d.get("date", ""), "topic": d.get("topic", ""),
                    "custom": bool(d.get("custom")),
                    "title": d.get("post", {}).get("cover_title", "").replace("\\n", " ").replace("\n", " "),
                    "urls": [s.get("url", "") for s in d.get("sources", [])],
                    "category": d.get("story", {}).get("category", "")})
    return out

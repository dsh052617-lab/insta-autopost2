"""GitHub 이슈로 초안 검토·승인을 주고받는다."""
from __future__ import annotations

import json
import os
import re

import requests

from common import repo

API = "https://api.github.com"
MARKER_RE = re.compile(r"<!-- insta-draft: (\{.*?\}) -->")

LABELS = {
    "draft": ("6E7781", "인스타 카드뉴스 초안"),
    "approved": ("1A7F37", "승인됨 — 예정 시각에 게시"),
    "published": ("8250DF", "인스타에 게시 완료"),
    "skipped": ("BF8700", "게시 안 함"),
}


def _h() -> dict:
    return {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json"}


def _req(method: str, path: str, **kw):
    r = requests.request(method, f"{API}/repos/{repo()}{path}", headers=_h(), timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API {method} {path} 실패: {r.status_code} {r.text[:300]}")
    return r.json() if r.text else {}


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
    _req("POST", f"/issues/{number}/comments", json={"body": text})


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


def read_marker(issue: dict) -> dict | None:
    m = MARKER_RE.search(issue.get("body") or "")
    return json.loads(m.group(1)) if m else None


def make_marker(data: dict) -> str:
    return f"<!-- insta-draft: {json.dumps(data, ensure_ascii=False)} -->"


def label_names(issue: dict) -> set[str]:
    return {l["name"] for l in issue.get("labels", [])}

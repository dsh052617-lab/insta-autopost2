"""설정 점검: 실제 게시 전에 키·토큰·폰트·이미지 주소·피드가 모두 동작하는지 확인하고 결과를 이슈로 남긴다.

  python src/check_setup.py            # Actions → '0. 설정 점검'에서 실행
  python src/check_setup.py --search   # Claude 웹 검색까지 확인 (약 10~20원)

비밀값(키·토큰)은 결과에 절대 적지 않는다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

from common import ROOT, load_config, next_post_slot, raw_url, slot_time  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str):
    def deco(fn):
        try:
            ok, detail = fn()
        except Exception as e:  # 점검 하나가 실패해도 나머지는 계속
            ok, detail = False, f"{type(e).__name__}: {str(e)[:400]}"
        results.append((name, ok, detail))
        print(("✅ " if ok else "❌ ") + name + " — " + detail)
        return fn
    return deco


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", action="store_true")
    args = ap.parse_args()
    cfg = load_config()

    @check("설정 파일(config.yaml)")
    def _():
        date, topic = next_post_slot(cfg)
        return True, f"다음 게시: {date} {slot_time(cfg, topic)} ({cfg['topics'][topic]['label']})"

    @check("한글 폰트")
    def _():
        import render
        render.font(40, True), render.font(40, False)
        return True, "Noto Sans CJK KR 확인"

    @check("Claude API 키 · 모델")
    def _():
        import writer
        c = writer.client()
        names = []
        for key in ("model", "research_model"):
            m = cfg["claude"].get(key)
            if m:
                c.models.retrieve(m)  # 요금 없음
                names.append(m)
        return True, "사용 가능: " + ", ".join(names)

    @check("Claude 결과 받기 (짧은 시험 호출)")
    def _():
        import writer
        tool = {"name": "ping", "description": "확인용", "input_schema": {
            "type": "object", "properties": {"ok": {"type": "string"}}, "required": ["ok"]}}
        r = writer._call_tool(cfg, "확인용 호출이야.", "ping 도구를 ok='네'로 호출해줘.", tool, max_tokens=500)
        return bool(r.get("ok")), f"{cfg['claude']['model']} 도구 호출 정상 (약 10~30원)"

    if args.search:
        @check("Claude 웹 검색 (내 주제·출처 보충용)")
        def _():
            import news
            import writer
            found = writer.research(cfg, "한국은행 기준금리 최근 결정", sorted(news.trusted_domains(cfg)))
            return bool(found.get("urls")), f"찾은 주소 {len(found.get('urls', []))}개"

    @check("뉴스 피드")
    def _():
        import news
        bad, total = [], 0
        for key, t in cfg["topics"].items():
            for f in t["feeds"]:
                try:
                    r = requests.get(f["url"], headers={"User-Agent": news.UA}, timeout=20)
                    r.raise_for_status()
                    total += 1
                except Exception as e:
                    bad.append(f"{f['url']} ({str(e)[:60]})")
        detail = f"정상 {total}개" + (f", 실패 {len(bad)}개: " + "; ".join(bad) if bad else "")
        return total >= 6, detail

    @check("카드 이미지 주소 (raw.githubusercontent.com)")
    def _():
        url = raw_url(ROOT / "README.md")
        code = requests.head(url, timeout=20, allow_redirects=True).status_code
        return code == 200, f"{code} (저장소가 Public이어야 인스타가 이미지를 가져갈 수 있어요)"

    @check("인스타 토큰 · 계정")
    def _():
        import instagram
        token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if not token:
            return False, "IG_ACCESS_TOKEN 시크릿이 비어 있어요 (게시 전까지 등록 필요)"
        kind = "IGAA(60일, 갱신 필요)" if instagram.is_instagram_login_token(token) else "EAA(시스템 사용자)"
        uid = os.environ.get("IG_USER_ID", "").strip() or instagram.my_user_id(token)
        info = instagram._get(uid, token, fields="username")
        limit = ""
        try:
            q = instagram._get(f"{uid}/content_publishing_limit", token, fields="quota_usage,config")
            row = (q.get("data") or [{}])[0]
            limit = f", 오늘 게시 {row.get('quota_usage', '?')}/{row.get('config', {}).get('quota_total', '?')}"
        except Exception:
            pass
        return True, f"토큰 {kind}, 계정 @{info.get('username', '?')} (ID {uid}){limit}"

    @check("인스타 게시 리허설 (실제로 올리지는 않음)")
    def _():
        """가장 최근 초안 이미지로 인스타 '게시 준비'까지만 해 본다. 마지막 게시 버튼(media_publish)은 누르지 않는다."""
        import json

        import instagram
        token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if not token:
            return False, "IG_ACCESS_TOKEN이 없어 건너뜀"
        drafts = sorted((ROOT / "drafts").glob("*/post.json"), key=lambda p: p.stat().st_mtime)
        if not drafts:
            return True, "아직 초안이 없어 건너뜀 (초안을 만든 뒤 다시 점검하면 확인돼요)"
        data = json.loads(drafts[-1].read_text(encoding="utf-8"))
        images = sorted((drafts[-1].parent / f"v{data['version']}").glob("*.jpg"))
        urls = [raw_url(p) for p in images]
        uid = os.environ.get("IG_USER_ID", "").strip() or instagram.my_user_id(token)
        children = []
        for u in urls:
            children.append(instagram._post(f"{uid}/media", token, image_url=u, is_carousel_item="true")["id"])
        for cid in children:
            instagram._wait_ready(cid, token)
        parent = instagram._post(f"{uid}/media", token, media_type="CAROUSEL",
                                 children=",".join(children), caption="리허설")["id"]
        instagram._wait_ready(parent, token)
        return True, (f"{drafts[-1].parent.name} 이미지 {len(urls)}장을 인스타가 정상으로 받아 게시 직전 단계까지 확인 "
                      "(실제 게시는 안 함, 준비본은 24시간 뒤 자동 삭제)")

    @check("GitHub 이슈·라벨 권한")
    def _():
        import github_api as gh
        gh.ensure_labels()
        return True, "라벨 확인·생성 완료"

    passed = all(ok for _, ok, _ in results)
    body = "\n".join(f"- {'✅' if ok else '❌'} **{name}** — {detail}" for name, ok, detail in results)
    summary = "모두 정상이에요. 자동 업로드 준비 완료!" if passed else "❌ 표시된 항목을 먼저 해결해 주세요."
    print("\n" + summary)
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_TOKEN"):
        import github_api as gh
        try:
            gh.create_issue(f"[설정 점검] {'✅ 정상' if passed else '❌ 확인 필요'}",
                            f"### 설정 점검 결과\n{summary}\n\n{body}\n\n실행 기록: {gh.run_link()}",
                            [] if passed else ["error"])
        except Exception as e:
            print(f"(결과 이슈 작성 실패: {e})")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

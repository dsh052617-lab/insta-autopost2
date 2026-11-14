"""Instagram 캐러셀 게시.

토큰 종류에 따라 주소가 달라요.
- IGAA… (예전 'Instagram 로그인' 방식, 60일)   → graph.instagram.com
- EAA…  ('통합 로그인'/시스템 사용자 토큰, 만료 없음) → graph.facebook.com
"""
from __future__ import annotations

import time

import requests

VERSION = "v26.0"


def is_instagram_login_token(token: str) -> bool:
    return token.startswith("IG")


def _base(token: str) -> str:
    host = "graph.instagram.com" if is_instagram_login_token(token) else "graph.facebook.com"
    return f"https://{host}/{VERSION}"


def _check(r: requests.Response) -> dict:
    data = r.json() if r.text else {}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        raise RuntimeError(f"Instagram API 오류 {r.status_code}: {err.get('message', r.text[:300])}")
    return data


def _post(path: str, token: str, **params) -> dict:
    return _check(requests.post(f"{_base(token)}/{path}", data={**params, "access_token": token}, timeout=60))


def _get(path: str, token: str, **params) -> dict:
    return _check(requests.get(f"{_base(token)}/{path}", params={**params, "access_token": token}, timeout=60))


def _wait_ready(container_id: str, token: str, timeout: int = 180) -> None:
    start = time.time()
    while time.time() - start < timeout:
        status = _get(container_id, token, fields="status_code,status").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            info = _get(container_id, token, fields="status")
            raise RuntimeError(f"인스타가 이미지를 처리하지 못했어요: {info}")
        time.sleep(4)
    raise TimeoutError("인스타 이미지 처리 대기 시간 초과")


def publish_carousel(ig_user_id: str, token: str, image_urls: list[str], caption: str,
                     ai_label: bool = True) -> dict:
    if not 2 <= len(image_urls) <= 10:
        raise ValueError("캐러셀은 이미지 2~10장이어야 해요.")
    children = []
    for url in image_urls:
        children.append(_post(f"{ig_user_id}/media", token, image_url=url, is_carousel_item="true")["id"])
        time.sleep(1)
    for cid in children:
        _wait_ready(cid, token)

    params = {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption}
    try:
        parent = _post(f"{ig_user_id}/media", token, **params,
                       **({"is_ai_generated": "true"} if ai_label else {}))["id"]
    except RuntimeError as e:
        if ai_label and "is_ai_generated" in str(e):
            print("⚠️  AI 라벨 파라미터가 거부돼 라벨 없이 다시 시도해요.")
            parent = _post(f"{ig_user_id}/media", token, **params)["id"]
        else:
            raise
    _wait_ready(parent, token)

    media_id = _post(f"{ig_user_id}/media_publish", token, creation_id=parent)["id"]
    permalink = ""
    try:
        permalink = _get(media_id, token, fields="permalink").get("permalink", "")
    except RuntimeError:
        pass
    return {"media_id": media_id, "permalink": permalink}


def my_user_id(token: str) -> str:
    """토큰으로 연결된 인스타 프로페셔널 계정 ID를 찾는다 (IG_USER_ID 시크릿이 없을 때)."""
    if is_instagram_login_token(token):
        me = _get("me", token, fields="user_id,username")
        print(f"   계정: @{me.get('username')}")
        return str(me.get("user_id") or me["id"])
    # 통합 로그인(시스템 사용자) 토큰: 할당된 인스타 계정 → 없으면 페이지에 연결된 계정
    for path, fields in (("me/assigned_instagram_accounts", "id,username"),
                         ("me/accounts", "instagram_business_account{id,username}")):
        try:
            data = _get(path, token, fields=fields).get("data", [])
        except RuntimeError:
            continue
        for row in data:
            acct = row.get("instagram_business_account", row)
            if acct.get("id"):
                print(f"   계정: @{acct.get('username', '?')} (ID {acct['id']})")
                return str(acct["id"])
    raise RuntimeError("토큰에 연결된 인스타 계정을 찾지 못했어요. GitHub Secrets에 IG_USER_ID를 넣어주세요.")


def refresh_token(token: str) -> dict:
    """장기 토큰(60일) 연장. 발급 후 24시간이 지나야 갱신 가능."""
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    return _check(r)

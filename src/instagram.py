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


HINTS = {
    190: "토큰이 만료됐거나 잘못됐어요. Meta 비즈니스 설정 → 시스템 사용자에서 토큰을 새로 만들어 IG_ACCESS_TOKEN을 바꿔주세요.",
    10: "토큰에 권한이 없어요. 토큰을 만들 때 instagram_basic, instagram_content_publish, pages_show_list, "
        "pages_read_engagement, business_management 권한을 모두 체크했는지 확인해주세요.",
    200: "토큰에 권한이 없어요. 시스템 사용자에게 인스타 계정(과 연결된 페이지) 자산이 '전체 권한'으로 할당됐는지 확인해주세요.",
    100: "요청 값이 잘못됐어요. IG_USER_ID가 인스타 '비즈니스 계정 ID'(17841…로 시작)인지 확인해주세요.",
    4: "요청이 너무 많아요. 1시간쯤 뒤에 다시 시도해주세요.",
    9: "인스타 게시 한도(하루 50개)에 걸렸어요. 내일 다시 시도해주세요.",
    36003: "이미지 비율이 맞지 않아요.",
    9004: "인스타가 이미지 주소를 열지 못했어요. 저장소가 공개(Public)인지 확인해주세요.",
}


class InstagramError(RuntimeError):
    def __init__(self, msg: str, code: int | None = None, transient: bool = False):
        super().__init__(msg)
        self.code = code
        self.transient = transient


def _check(r: requests.Response) -> dict:
    try:
        data = r.json() if r.text else {}
    except ValueError:
        data = {"error": {"message": r.text[:300]}}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        code = err.get("code")
        sub = err.get("error_subcode")
        hint = HINTS.get(sub) or HINTS.get(code) or ""
        transient = bool(err.get("is_transient")) or r.status_code >= 500 or code in (1, 2, 4, 17, 32, 613)
        msg = f"Instagram API 오류 {r.status_code} (code {code}/{sub}): {err.get('message', r.text[:300])}"
        raise InstagramError(msg + (f"\n→ {hint}" if hint else ""), code, transient)
    return data


def _call(method: str, path: str, token: str, retry: bool, **params) -> dict:
    url = f"{_base(token)}/{path}"
    for attempt in range(4 if retry else 1):
        try:
            if method == "GET":
                r = requests.get(url, params={**params, "access_token": token}, timeout=60)
            else:
                r = requests.post(url, data={**params, "access_token": token}, timeout=90)
            return _check(r)
        except requests.RequestException as e:
            err: Exception = InstagramError(f"인스타 서버 접속 실패: {e}", transient=True)
        except InstagramError as e:
            err = e
        if not (retry and getattr(err, "transient", False)) or attempt == 3:
            raise err
        time.sleep(10 * (attempt + 1))
    raise RuntimeError("unreachable")


def _post(path: str, token: str, retry: bool = True, **params) -> dict:
    return _call("POST", path, token, retry, **params)


def _get(path: str, token: str, **params) -> dict:
    return _call("GET", path, token, True, **params)


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
        if ai_label and ("is_ai_generated" in str(e) or getattr(e, "code", None) == 100):
            print("⚠️  AI 라벨 파라미터가 거부돼 라벨 없이 다시 시도해요.")
            parent = _post(f"{ig_user_id}/media", token, **params)["id"]
        else:
            raise
    _wait_ready(parent, token)

    # 게시 요청은 중복 게시를 막기 위해 자동 재시도하지 않는다
    media_id = _post(f"{ig_user_id}/media_publish", token, retry=False, creation_id=parent)["id"]
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
    for path, fields in (("me/accounts", "instagram_business_account{id,username}"),
                         ("me/assigned_instagram_accounts", "id,username")):
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

"""인스타 토큰 진단: 토큰 값은 출력하지 않는다."""
import os, requests
tok = os.environ["IG_ACCESS_TOKEN"].strip()
uid = os.environ.get("IG_USER_ID", "").strip() or "17841454174005348"
host = "graph.instagram.com" if tok.startswith("IG") else "graph.facebook.com"
base = f"https://{host}/v21.0"
def show(name, path, **params):
    params["access_token"] = tok
    try:
        r = requests.get(f"{base}/{path}", params=params, timeout=30)
        body = r.text.replace(tok, "***")[:600]
        print(f"[{name}] HTTP {r.status_code}: {body}")
    except Exception as e:
        print(f"[{name}] 예외: {e}")
print("토큰 종류:", "IGAA" if tok.startswith("IG") else tok[:3] + "…", "/ host", host)
show("me", "me", fields="id,name")
show("permissions", "me/permissions")
show("debug_token", "debug_token", input_token=tok)
show("ig account", uid, fields="username,account_type")
show("publish limit", f"{uid}/content_publishing_limit", fields="quota_usage,config")
show("me/accounts", "me/accounts", fields="name,instagram_business_account{id,username}")

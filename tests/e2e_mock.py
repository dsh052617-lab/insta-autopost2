"""외부 접속 없이 전체 흐름을 시험하는 모의(mock) 테스트.
뉴스·Claude·GitHub·Instagram을 가짜로 바꿔서 초안 → 내 주제 → 승인 → 게시 흐름을 확인한다.
실행: python tests/e2e_mock.py  (끝나면 drafts/ 와 data/history.json 을 원래대로 돌려놓을 것)
"""
import json, sys, os, copy, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ["GITHUB_REPOSITORY"] = "me/insta-autopost"
import news, writer, github_api as gh, instagram, common
cfg = common.load_config()
good = json.load(open(ROOT / "tests" / "sample_post.json", encoding="utf-8"))
TEXT = {"https://www.bok.or.kr/a": "한국은행 금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 현 수준인 연 2.50%로 유지하기로 하였다. " * 10,
        "https://www.yna.co.kr/b": "소비자물가 상승률은 2% 내외에서 안정되고 있다고 밝혔다. " * 20,
        "https://www.fsc.go.kr/c": "금융위원회는 청년도약계좌 제도를 개편한다. 기준금리를 현 수준인 연 2.50%로 유지하기로 하였다. 소비자물가 상승률은 2% 내외에서 안정 " * 10,
        "https://random-blog.com/x": "블로그 " * 300}
class R:
    def __init__(s, url): s.url = url; s.text = "<html><article><p>" + TEXT.get(url, "") + "</p></article></html>"
    def raise_for_status(s): pass
news.requests.get = lambda url, **k: R(url)
import trafilatura
trafilatura.extract = lambda html, **k: html.replace("<html><article><p>", "").replace("</p></article></html>", "")
trafilatura.extract_metadata = lambda html: None
ITEMS = [{"title": "통화정책방향 결정", "url": "https://www.bok.or.kr/a", "source": "한국은행", "tier": "official", "summary": "", "published": "2026-11-13", "ts": 2},
         {"title": "한은 기준금리 동결", "url": "https://www.yna.co.kr/b", "source": "연합뉴스", "tier": "press", "summary": "", "published": "2026-11-13", "ts": 1}]
news.collect = lambda cfg, feeds, lb, ex, **k: ITEMS
writer.select_story = lambda *a, **k: {"indices": [0, 1], "angle": "a", "reason": "r"}
writer.write_post = lambda *a, **k: copy.deepcopy(good)
writer.revise_post = lambda *a, **k: copy.deepcopy(good)
writer.research = lambda cfg, topic, domains, avoid=None: {"urls": ["https://random-blog.com/x", "https://www.fsc.go.kr/c", "https://www.yna.co.kr/b"], "category": "economy", "angle": "취준생"}
ISS = {}
gh.ensure_labels = lambda: None
def create(title, body, labels):
    n = len(ISS) + 1; ISS[n] = {"number": n, "title": title, "body": body, "labels": [{"name": l} for l in labels], "state": "open", "html_url": f"https://github.com/x/{n}"}; return ISS[n]
gh.create_issue = create; gh.get_issue = lambda n: ISS[n]; gh.update_issue = lambda n, **f: ISS[n].update(f)
gh.comment = lambda n, t: print(f"   💬 #{n}: {t.splitlines()[0]}")
gh.add_labels = lambda n, ls: ISS[n]["labels"].extend({"name": l} for l in ls)
gh.remove_label = lambda n, l: ISS[n].update(labels=[x for x in ISS[n]["labels"] if x["name"] != l])
gh.open_drafts = lambda: [i for i in ISS.values() if i["state"] == "open" and "draft" in gh.label_names(i)]
pub = []
instagram.publish_carousel = lambda uid, tok, urls, cap, ai_label: pub.append((urls, cap)) or {"media_id": str(len(pub)), "permalink": "https://instagram.com/p/x"}
os.environ.update(IG_USER_ID="1", IG_ACCESS_TOKEN="t")
import draft, handle_comment, publish, custom
print("=== 주간 자동 (경제)")
sys.argv = ["draft.py", "--topic", "economy"]; draft.main()
print("TITLE:", ISS[1]["title"])
print("=== 내 주제 요청 (이슈 #2)")
create("주제: 청년도약계좌 바뀐 점", "취준생 입장에서", [])
sys.argv = ["custom.py", "--topic", "청년도약계좌 바뀐 점", "--detail", "취준생 입장에서 https://evil.com/x", "--issue", "2"]; custom.main()
print("TITLE:", ISS[2]["title"], gh.label_names(ISS[2]))
b = ISS[2]["body"]; print(b[:250]); print(b[b.index("### 참고"):b.index("### 캡션")])
os.environ.update(ISSUE_NUMBER="2", COMMENT_BODY="승인"); handle_comment.main()
print("custom published:", len(pub), ISS[2]["state"])
print("=== 예정 시각 게시 (주간분만)")
os.environ.update(ISSUE_NUMBER="1", COMMENT_BODY="승인"); handle_comment.main()
d = dt.date.fromisoformat(gh.read_marker(ISS[1])["date"])
publish.now = lambda c: common.post_datetime(c, d) + dt.timedelta(minutes=1)
sys.argv = ["publish.py"]; publish.main()
print("total published:", len(pub), "| history:", [h["title"] for h in common.load_history()])

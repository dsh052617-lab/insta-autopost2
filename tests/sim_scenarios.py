"""운영 시뮬레이션: 외부 접속 없이 하루 흐름 전체(등록→승인→예약 게시→늦은 승인→다음 날)를 가짜 시계로 돌린다."""
import json, sys, os, copy, re, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ["GITHUB_REPOSITORY"] = "me/insta-autopost"
import news, writer, github_api as gh, instagram, common, trafilatura
cfg = common.load_config()
KST = common.tz(cfg)
CLOCK = [dt.datetime(2026, 11, 15, 14, 0, tzinfo=KST)]
def fake_now(c=None): return CLOCK[0]
common.now = fake_now
FAILS = []
def check(name, cond, extra=""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f" — {extra}" if extra and not cond else ""))
    if not cond: FAILS.append(name)

# ---- 출처 원문 (가짜) ----
eco_spec = json.loads(re.search(r"```json\n(.*)\n```", (ROOT/"tests/_eco_body.md").read_text(), re.S).group(1))
def page_text(url, spec):
    ev = [c["evidence"] for c in spec["post"]["claims"] if spec["sources"][c["source"]-1] == url]
    filler = " 16일 24시간 12월 8개월 2026년 11월 15일 금융위원회는 밝혔다. " * 10
    return " ".join(ev) + filler
TEXT = {u: page_text(u, eco_spec) for u in eco_spec["sources"]}
ai_spec = copy.deepcopy(eco_spec); ai_spec["topic"] = "ai"; ai_spec["category"] = "정책·규제"
ai_spec["sources"] = ["https://www.yna.co.kr/ai1", "https://www.hani.co.kr/ai2"]
ai_spec["post"]["cover_title"] = "AI 기본법 시행령\n입법예고 시작"
TEXT.update({u: page_text(eco_spec["sources"][i], eco_spec) for i, u in enumerate(ai_spec["sources"])})
class R:
    def __init__(s, url): s.url = url; s.text = TEXT.get(url, ""); s.content = s.text.encode()
    def raise_for_status(s):
        if s.url not in TEXT: raise RuntimeError("403 차단")
news.requests.get = lambda url, **k: R(url)
trafilatura.extract = lambda html, **k: html.decode() if isinstance(html, bytes) else html
trafilatura.extract_metadata = lambda html: None

# ---- 가짜 GitHub ----
ISS, COMMENTS, DISPATCH = {}, {}, []
gh.ensure_labels = lambda: None
def create(title, body, labels=()):
    n = len(ISS) + 1
    ISS[n] = {"number": n, "title": title, "body": body, "labels": [{"name": l} for l in labels], "state": "open",
              "html_url": f"https://github.com/x/{n}", "closed_at": None}
    COMMENTS[n] = []; return ISS[n]
gh.create_issue = create
gh.get_issue = lambda n: ISS[n]
def upd(n, **f):
    ISS[n].update(f)
    if f.get("state") == "closed": ISS[n]["closed_at"] = CLOCK[0].astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
gh.update_issue = upd
def com(n, t): COMMENTS[n].append(t); print(f"     💬 #{n}: {t.splitlines()[0][:90]}")
gh.comment = com
gh.list_comments = lambda n: [{"body": c} for c in COMMENTS[n]]
gh.add_labels = lambda n, ls: ISS[n]["labels"].extend({"name": l} for l in ls if l not in gh.label_names(ISS[n]))
gh.remove_label = lambda n, l: ISS[n].update(labels=[x for x in ISS[n]["labels"] if x["name"] != l])
gh.open_drafts = lambda: [i for i in ISS.values() if i["state"] == "open" and "draft" in gh.label_names(i)]
gh.recent_drafts = lambda: [i for i in ISS.values() if "draft" in gh.label_names(i)]
gh.dispatch_publish = lambda: DISPATCH.append(CLOCK[0])
gh.report_error = lambda e, where, n=0: print(f"     🛑 오류 보고({where}): {e}")
PUB = []
instagram.publish_carousel = lambda uid, tok, urls, cap, ai_label: PUB.append((CLOCK[0], cap[:20])) or {"media_id": str(len(PUB)), "permalink": f"https://instagram.com/p/{len(PUB)}"}
os.environ.update(IG_USER_ID="1", IG_ACCESS_TOKEN="t")
import manual, handle_comment, publish, draft
for m in (manual, publish, draft): m.now = fake_now
publish.requests.head = lambda url, **k: type("H", (), {"status_code": 200})()
def sleep(sec): CLOCK[0] += dt.timedelta(seconds=sec)
publish.time.sleep = sleep
common.save_history([])

def at(h, m, day=15): CLOCK[0] = dt.datetime(2026, 11, day, h, m, tzinfo=KST)
def register(spec, title):
    i = create(title, "```json\n" + json.dumps(spec, ensure_ascii=False) + "\n```")
    sys.argv = ["manual.py", "--issue", str(i["number"])]
    try: manual.main(); return i["number"], True
    except SystemExit: return i["number"], False
def say(n, text):
    os.environ.update(ISSUE_NUMBER=str(n), COMMENT_BODY=text); handle_comment.main()
def run_publish():
    sys.argv = ["publish.py"]
    try: publish.main()
    except SystemExit: pass

print("① 10:00 아침 작업이 경제·AI 정기 초안 등록")
at(10, 5)
e, ok = register(eco_spec, "직접: [11/15 경제] 불법사금융"); check("경제 초안 등록·검증 통과", ok and "draft" in gh.label_names(ISS[e]))
a, ok = register(ai_spec, "직접: [11/15 AI] AI 기본법"); check("AI 초안 등록·검증 통과", ok and "draft" in gh.label_names(ISS[a]))
check("초안 날짜·시간 마커", gh.read_marker(ISS[e])["date"] == "2026-11-15" and gh.read_marker(ISS[a])["topic"] == "ai")

print("② 같은 날 경제 초안을 또 만들려 하면 거절")
d, ok = register(eco_spec, "직접: [11/15 경제] 중복"); check("중복 초안 거절", not ok and "이미 있어요" in COMMENTS[d][-1])

print("③ 18:00 경제만 승인")
at(18, 0); say(e, "승인")
check("승인 라벨", "approved" in gh.label_names(ISS[e])); check("즉시 게시 안 됨", len(PUB) == 0)

print("④ 19:35 예약 실행 → 경제 20:00 게시, AI는 다음 실행 몫")
at(19, 35); run_publish()
check("경제 20:00 정각 게시", len(PUB) == 1 and PUB[0][0].strftime("%H:%M") == "20:00", str(PUB))
check("AI는 이번 실행에서 게시 안 함", ISS[a]["state"] == "open")

print("⑤ 20:12 예비 실행 → 중복 게시 없음")
at(20, 12); run_publish(); check("중복 게시 없음", len(PUB) == 1)

print("⑥ AI 미승인 상태로 20:35 실행 → 21:00에 보류 안내")
at(20, 35); run_publish()
check("미승인 → 게시 안 함", len(PUB) == 1); check("보류 안내 댓글", any("⏸" in c for c in COMMENTS[a]))
at(21, 12); run_publish(); check("예비 실행이 안내를 또 달지 않음", sum("⏸" in c for c in COMMENTS[a]) == 1)

print("⑦ 21:20 늦게 승인 → 게시 작업 즉시 재실행")
at(21, 20); say(a, "승인")
check("게시 작업 재실행 요청", len(DISPATCH) == 1)
at(21, 23); run_publish(); check("늦은 승인분 게시", len(PUB) == 2)

print("⑧ 다음 날: 지난 초안 승인 시도·자동 정리")
x, ok = register(dict(copy.deepcopy(eco_spec), date="2026-11-16", topic="economy"), "직접: [11/16 경제] 같은 사건")
check("이미 게시한 사건과 겹치면 정기 초안 거절", not ok and "겹쳐서" in COMMENTS[x][-1])
fu = copy.deepcopy(eco_spec); fu["date"] = "2026-11-16"; fu["followup"] = {"of": "불법사금융", "new": "첫날 신청 건수 발표"}
f, ok = register(fu, "직접: [11/16 경제] 후속")
check("새 기사 없는 '후속'은 거절", not ok and "후속 보도로 올리려면" in COMMENTS[f][-1])
old = create("old", ISS[a]["body"].replace('"date": "2026-11-15"', '"date": "2026-11-14"'), ["draft"])
at(19, 35, day=16); say(old["number"], "승인")
check("지난 날짜 초안 승인 거절", "approved" not in gh.label_names(old) and "지나서" in COMMENTS[old["number"]][-1])
run_publish(); check("지난 초안 자동 정리", old["state"] == "closed" and "skipped" in gh.label_names(old))

print("⑨ 미리 게시된 초안은 그날 자리를 막지 않음")
pre = create("pre", ISS[e]["body"].replace('"date": "2026-11-15"', '"date": "2026-11-17"').replace("2026-11-15-economy","x"), ["draft", "published"])
pre["state"] = "closed"; pre["closed_at"] = "2026-11-16T05:00:00Z"
good = json.load(open(ROOT / "tests" / "sample_post.json", encoding="utf-8"))
TEXT["https://www.bok.or.kr/a"] = "한국은행 금융통화위원회는 다음 통화정책방향 결정시까지 한국은행 기준금리를 현 수준인 연 2.50%로 유지하기로 하였다. " * 10
TEXT["https://www.yna.co.kr/b"] = "소비자물가 상승률은 2% 내외에서 안정되고 있다고 밝혔다. " * 20
ITEMS = [{"title": "통화정책방향 결정", "url": "https://www.bok.or.kr/a", "source": "한국은행", "tier": "official", "summary": "", "published": "2026-11-17", "ts": 2},
         {"title": "한은 기준금리 동결", "url": "https://www.yna.co.kr/b", "source": "연합뉴스", "tier": "press", "summary": "", "published": "2026-11-17", "ts": 1}]
news.collect = lambda *a, **k: ITEMS
writer.select_story = lambda *a, **k: {"indices": [0, 1], "angle": "a", "reason": "r"}
writer.write_post = lambda *a, **k: copy.deepcopy(good)
writer.classify_category = lambda *a, **k: ""
at(12, 53, day=17); before = len(ISS)
sys.argv = ["draft.py", "--topic", "economy"]
try: draft.main()
except SystemExit: pass
check("조기 게시분이 있어도 그날 예비 초안 생성", len(ISS) == before + 1)
at(12, 54, day=17); before = len(ISS)
try: draft.main()
except SystemExit: pass
check("이미 그날 초안이 있으면 예비 초안 건너뜀", len(ISS) == before)

print("⑩ 이미지 주소가 안 열리면 게시 대신 오류 안내")
g_spec = copy.deepcopy(ai_spec); g_spec["date"] = "2026-11-17"; g_spec["post"]["cover_title"] = "반도체 수출\n역대 최대 기록"
g_spec["sources"] = ["https://www.yna.co.kr/z1", "https://www.hani.co.kr/z2"]
TEXT.update({u: page_text(eco_spec["sources"][i], eco_spec) for i, u in enumerate(g_spec["sources"])})
for c in g_spec["post"]["claims"]: pass
at(10, 5, day=17); g, ok = register(g_spec, "직접: [11/17 AI] 다른 사건")
check("다른 사건 정기 초안 등록", ok)
publish.requests.head = lambda url, **k: type("H", (), {"status_code": 404})()
at(20, 0, day=17); say(g, "승인") if ok else None
at(20, 35, day=17); run_publish()
check("실패 시 오류 댓글·게시 안 함", any("게시에 실패" in c for c in COMMENTS[g]) and ISS[g]["state"] == "open")

print("\n결과:", "모두 통과" if not FAILS else f"실패 {len(FAILS)}개: {FAILS}")
print("게시 기록:", [(t.strftime('%m/%d %H:%M'), c) for t, c in PUB])

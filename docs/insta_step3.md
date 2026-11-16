# 인스타 카드뉴스 초안 만들기 (아침 예약 작업의 Step 3)

아침 예약 작업(경제 시사 / AI 산업 이슈)이 브리핑을 끝낸 뒤 이 문서를 처음부터 끝까지 읽고 그대로 따른다.
이 문서가 예약 작업 지시문의 안전 규칙과 다르면 지시문을 우선한다.

- 계정: 인스타그램 @agi.economy.kr, 프로젝트 "AGI시대 경제"
- TOPIC: 지시문이 정해 준 값 (`economy` 또는 `ai`)
- POST_DATE: 오늘 (`TZ=Asia/Seoul date +%Y-%m-%d`)
- 게시 시각: economy 20:00, ai 21:00 (승인해야만 게시됨)
- R = `repos/dsh052617-lab/insta-autopost2`. GitHub 읽기·쓰기 방법은 `docs/insta_connect.md`를 따른다(gh api가 막히면 GitHub MCP 도구로 같은 일을 한다).

## 안전 규칙 (가장 중요)
- 이슈를 만들고, 확인하고, 실패한 내 원고 이슈를 닫는 것 외에는 GitHub 이슈에 아무것도 하지 않는다.
- 명령 댓글(승인·지금 게시·취소·날짜·수정)을 절대 달지 않는다. 게시는 사람이 픽스에서 승인해야만 된다.
- 사실(숫자·날짜·기관·인물·발표 내용)은 연 출처 본문에 있는 것만 쓴다. 기억으로 숫자를 쓰지 않는다.

## 1) 중복 확인
`gh api "$R/issues?labels=draft&state=all&per_page=30"` 과 `gh api "$R/issues?state=open&per_page=30"` 에서
본문 마커 `<!-- insta-draft: {...} -->`의 date == POST_DATE, topic == TOPIC, custom == false 인 이슈 중
① 열려 있는 것, 또는 ② published 라벨로 닫혔고 closed_at을 한국 시간으로 바꾼 날짜가 POST_DATE인 것이 있으면 여기서 끝낸다(메시지 없음).
(취소된 것과, 예정일보다 먼저 게시된 것은 막지 않는다.)
제목이 "직접:"으로 시작하고 같은 날짜·주제인 열린 이슈가 있어도 끝낸다.
`data/skip/<POST_DATE>-<TOPIC>.txt` 파일이 이미 있어도 끝낸다(오늘은 이미 오후로 넘겼거나 쉬기로 한 날).

## 2) 이미 다룬 것 피하기 (절대 규칙, 기간 제한 없음)
지금까지 게시했거나 게시 예정인 모든 글 — AI·경제·내 주제 모두, `data/history.json` 전체와 열린 draft 이슈·"직접:" 이슈의 제목·출처 URL — 과
같은 사건·같은 소재는 고르지 않는다. 같은 회사·같은 정책이라도 새 내용이 없으면 제외한다.

예외(후속 보도): 그 사건에 새로 추가된 내용(새 발표·새 수치·새 조치·새 결정)이 있고, 그것이 이전 글 날짜 이후에 게시된 허용 출처 기사로 확인되면 올릴 수 있다.
이때는 새 내용을 중심으로 쓰고(이전 글 반복 금지), 원고 JSON에 `"followup":{"of":"<이전 글 제목>","new":"<새로 추가된 내용 한 줄>"}`을 넣고,
sources에 이전 글 이후 게시된 기사를 1건 이상 넣는다(없으면 프로그램이 거절한다).

최근 2개 게시물의 분야(category)와 같은 분야도 피한다. 취업·고용·일자리 이야기는 연달아 고르지 않는다.

## 3) 고르기
방금 픽스에 저장한 오늘 브리핑의 items 중에서 카드뉴스 1개를 고른다. 기준(중요한 순서):
1. 최근 7일 가장 비중 있는 이슈(여러 매체·기관이 다룬 것, 정책·제도·시장에 실제 변화를 만든 것). 비중이 비슷하면 더 최근 것.
2. 일반 국민(대학생·사회초년생 포함)의 삶과 결정에 실질적으로 도움이 되는 정보
3. 자극적 사건·사생활·루머·전망만 있는 기사·단순 주가 등락·광고성 기사는 제외 (사건의 경제·산업적 영향만 다룬다)
4. (ai만) 새 AI 도구·제품·모델 출시 소식은 다른 후보가 정말 없을 때만

items가 모두 부적합하거나, 모두 겹치고 후속 보도도 아니거나, 브리핑에 항목이 없으면 **3-F) 오후로 넘기기**로 간다.

### 3-F) 오후로 넘기기 (대체 카드는 지금 만들지 않는다)
clone 폴더에 `data/skip/<POST_DATE>-<TOPIC>.txt`를 만들어 첫 줄에 정확히 `pending-fallback`, 둘째 줄에 한 줄 이유를 적고
`git add`, `git commit -m "fallback pending: <POST_DATE> <TOPIC>"`, `git pull --rebase -q`, `git push -q`.
(낮 12시 17분 '인스타 대체 카드 (오후)' 작업이 이 표시를 보고 economy는 용어·경제사 카드, ai는 모델 비교 카드를 만든다.)
메시지: economy는 "📮 인스타 초안 · 오늘은 주요 경제 이슈가 없어 낮 12시 반쯤 대체 카드(용어·경제사)를 만들어요",
ai는 "📮 인스타 초안 · 오늘은 주요 AI 이슈가 없어 낮 12시 반쯤 대체 카드(모델 비교)를 확인해요". 그리고 끝낸다.

## 4) 같은 사건의 기사 2~4개 모으기
브리핑 출처 1개로 끝내지 않는다. 고른 사건 하나를 여러 각도에서 다룬 기사를 WebSearch로 더 찾는다.
- 각도 예: ① 무슨 일이 있었나(공식 발표 원문 우선) ② 반응·영향(정부·시장·업계) ③ 독자에게 의미(생활·투자제도·일자리 등)
- 모두 '같은 사건'이어야 한다. 비슷한 주제의 다른 사건을 섞지 않는다(짜깁기 금지). 모든 기사는 최근 7일 이내, 최신일수록 우선.
- `config.yaml`의 sources 도메인에 있는 페이지만. 조건: 공식 발표(tier official) 1건 이상, 또는 서로 다른 언론사 2곳 이상(같은 통신사 기사를 실은 경우는 1곳).
- 검증 프로그램(GitHub)이 본문을 가져오지 못하는 곳은 출처로 넣지 않는다: 한국경제(hankyung.com)·뉴스1(news1.kr)·서울경제(sedaily.com)는 접속 차단,
  조선일보(chosun.com)·기획재정부(moef.go.kr)는 본문을 읽지 못함, 금융위원회(fsc.go.kr)는 접속이 자주 끊김, 유료 페이지(Bloomberg·WSJ·FT)·LMArena·Stanford AI Index도 실패.
  이런 곳의 내용은 같은 사건을 다룬 연합뉴스·뉴시스·매일경제·머니투데이·이데일리·파이낸셜뉴스·헤럴드경제·아시아경제·이투데이·동아일보·한겨레·경향신문 등으로 대신한다.
  한국은행 보도자료는 읽히는 것도 있으니 시도해 보고, 안 되면 그 발표를 보도한 기사로 대신한다. 최신 점검 결과는 `data/source_probe.md`.
- **출처 본문 미리 보기(권장)**: 검증 프로그램이 실제로 읽는 본문을 그대로 받아 볼 수 있다.
  `gh api -X POST $R/actions/workflows/fetch.yml/dispatches -f ref=main -f "inputs[urls]=<주소들 띄어쓰기 구분>"` → 1~2분 뒤 `git pull -q` →
  `preview/fetched/NN.txt` (첫 줄들에 URL·SOURCE·PUBLISHED, 그 아래 본문. "가져오지 못함"이면 그 출처는 쓰지 않는다).
  evidence는 이 본문에서 글자 그대로 복사하면 검증을 통과한다. 기사 주소를 못 찾겠으면 같은 작업에 `-f "inputs[queries]=<검색어1>|<검색어2>"`를 주면
  `preview/found.txt`에 신뢰 출처 기사 주소 목록이 생긴다.
- 카드의 각 장은 어느 기사에서 왔는지 claims로 연결되니, 기사마다 맡는 각도가 분명하게.

## 5) 원고 작성 — `tests/sample_post.json`과 같은 형식
- 숫자는 원문 표기 그대로. 카드·캡션·그래프에 나오는 모든 숫자는 출처 본문에도 있어야 한다(프로그램이 검사한다).
- cover_kicker 10자, cover_title 두 줄(`\n`, 줄마다 11자 이내), cover_subtitle 28자,
  slides 3~4장(heading 16자, highlight 10자 또는 "", points 1~3개 각 32자·가장 중요한 단어 하나만 **굵게**, terms 0~2개 {term 12자, meaning 32자}),
  takeaways 2~3개(24자), question 40자, caption 300자(첫 줄 핵심 사실, 이모지·느낌표·해시태그·출처 금지),
  hashtags 최대 8개(# 없이, 첫 번째 "AGI시대경제"),
  needs_disclaimer(특정 기업·종목·코인·금융상품이 나오거나 투자 판단으로 오해될 수 있으면 true).
- 말투: 차분한 해설 기사 톤의 해요체. 전문용어는 points에서 풀지 말고 terms에. 마지막 본문 카드는 독자에게 미치는 영향·확인할 점.
- claims: 카드·캡션·그래프의 모든 사실마다 {claim, source(sources 배열의 1부터 번호), evidence(그 페이지 본문에서 글자 그대로 복사한 15~150자 구절)}.

## 6) 이슈 만들기
아래 JSON을 본문 ```json 블록에 넣어
`gh api $R/issues -f title="직접: [M/D 경제] <cover_title 한 줄>" -F body=@<파일>` (ai면 `[M/D AI]`). 응답의 number, html_url을 기록한다.

```
{"mode":"scheduled","date":POST_DATE,"topic":TOPIC,"kind":"news","category":"<분야>",
 "reason":"<왜 골랐는지 한두 문장>","angle":"<관점 한 문장>","sources":["<출처 URL>", ...],
 "followup":<후속 보도일 때만 {"of":"...","new":"..."}, 아니면 이 키를 넣지 않는다>,
 "post":{...원고...}}
```
category — economy: 금리·통화/물가·생활비/부동산·주거/금융·투자제도/고용·소득/무역·환율/재정·세금/산업·기업/글로벌 경제 중 하나.
ai: 기술·모델/산업·기업/정책·규제/일자리·교육/생활·서비스/안전·윤리/반도체·인프라 중 하나.

## 7) 확인
이슈를 만들면 GitHub 작업 '6. 직접 만든 원고 등록'이 자동으로 돈다(1~3분).
- 2분 뒤 `gh api $R/issues/<번호>/comments`를 본다. github-actions[bot] 댓글이 하나도 없으면
  `gh api -X POST $R/actions/workflows/manual.yml/dispatches -f ref=main -f "inputs[issue]=<번호>"`로 한 번 직접 실행한다.
- 최대 6분 동안 30초 간격으로 댓글을 확인한다.
  - "🆕 초안을 본문에 올렸어요" → 성공.
  - "출처 검증을 통과하지 못했어요" / "가져오지 못했어요" / "원고에 …" / "공식 발표가 없고…" → 문제 항목만 고친 원고로 새 이슈를 한 번 더 만든다
    (가져오지 못한 출처는 같은 사건을 다룬 다른 허용 출처로 교체). 이전 이슈가 열려 있으면 `gh api -X PATCH $R/issues/<번호> -f state=closed`로 닫는다.
  - "이미 게시했거나…겹쳐서" → 브리핑의 다른 항목으로 새로 만든다. 다른 항목이 없으면 3-F)로 간다.
  - 다시 만들기는 최대 2번. 그래도 실패하면 실패한 이슈를 닫고 3-F)로 간다.

## 8) 픽스 동기화
`git -C <clone> pull -q` 후 `python3 <clone>/src/pix_sync.py --days 7` (pyyaml이 없으면 `pip install -q pyyaml --break-system-packages`).
출력 JSON 배열의 각 항목을 ArtifactData action "set", url "https://claude.ai/artifact/BKu81S9yMm9Z8zU9wyqhFZ", collection "insta",
doc_id = 항목.id, data = 항목.data 그대로 저장한다(값을 바꾸거나 줄이지 않는다. 버전 충돌이면 get 후 if_version으로 한 번 더). 실패해도 9)로 간다.

## 9) 결과 메시지 (SendUserMessage, 최종 답변도 같은 내용)
첫 줄(알림 미리보기): "📮 인스타 초안 · <cover_title 한 줄> (오늘 20:00 게시 예정, 승인 필요)" — ai면 21:00.
둘째 줄: "픽스 뉴스 탭에서 승인·수정할 수 있어요 · <이슈 링크>". 검증 실패로 끝났으면 그 사실도 한 줄로.

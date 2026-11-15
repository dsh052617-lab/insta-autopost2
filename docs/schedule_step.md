Step 3 — 인스타 카드뉴스 초안 (@agi.economy.kr, 프로젝트 "AGI시대 경제"). 브리핑 저장·메시지가 끝난 뒤에 한다. 실패해도 위 브리핑은 그대로 둔다.

TOPIC = "{TOPIC}"  (ai 또는 economy), POST_DATE = TODAY(Asia/Seoul, `TZ=Asia/Seoul date +%Y-%m-%d`).

0) 저장소 연결: add_repo(owner "dsh052617-lab", repo "insta-autopost2", access "push") 후 안내대로 clone. 실패하면 Step 3 전체를 건너뛰고, 마지막 메시지 끝에 "⚠️ 인스타 초안: GitHub 연결이 필요해요 (claude.ai 설정에서 GitHub 연결)" 한 줄만 덧붙인다. (낮 12시 53분에 예비 초안이 자동으로 만들어진다.)
1) 중복 확인: `gh issue list -R dsh052617-lab/insta-autopost2 --label draft --state all --limit 30 --json number,title,body` 에서 본문 마커 `<!-- insta-draft: {...} -->`의 date == POST_DATE, topic == TOPIC, custom == false 인 것이 있으면 Step 3 종료. 제목이 "직접:"으로 시작하고 같은 날짜·주제인 열린 이슈가 있어도 종료.
2) 이미 다룬 것 피하기: 저장소의 data/history.json 과 열린 draft 이슈의 제목·출처 URL을 읽는다. 같은 사건·같은 기사는 고르지 않는다. 최근 2개 게시물의 분야(category)와 같은 분야도 피한다. 특히 취업·고용·일자리 이야기는 연달아 고르지 않는다.
3) 고르기: 방금 픽스에 저장한 이 브리핑의 items 중에서 카드뉴스 1개를 고른다. 기준(중요한 순서):
   ① 지난 24시간 가장 비중 있는 이슈(여러 매체·기관이 다룬 것, 정책·제도·시장에 실제 변화를 만든 것)
   ② 일반 국민(대학생·사회초년생 포함)의 삶과 결정에 실질적으로 도움이 되는 정보
   ③ 자극적 사건·사생활·루머·전망만 있는 기사·단순 주가 등락·광고성 기사는 제외 (사건의 경제·산업적 영향만 다룬다)
   ④ 새 AI 도구·제품·모델 출시 소식은 다른 후보가 정말 없을 때만 (최후의 선택)
   items가 모두 부적합하면 Step 3 종료(메시지에 "오늘은 카드뉴스로 만들 이슈가 없어 건너뛰었어요" 한 줄).
4) 같은 사건의 기사 2~4개 모으기 (브리핑 출처 1개로 끝내지 않는다): 고른 사건 하나를 여러 각도에서 다룬 기사를 WebSearch로 더 찾는다.
   - 각도 예: ① 무슨 일이 있었나(공식 발표 원문 우선) ② 반응·영향(정부·시장·업계) ③ 독자에게 의미(생활·투자제도·일자리 등)
   - 모두 '같은 사건'이어야 한다. 비슷한 주제의 다른 사건을 섞지 않는다(짜깁기 금지). 핵심 사건은 지난 24~48시간 소식, 반응·영향 기사는 7일 이내까지 허용.
   - 저장소 config.yaml의 sources 도메인에 있는 페이지만. 조건: 공식 발표(tier official) 1건 이상, 또는 서로 다른 언론사 2곳 이상(같은 통신사 기사를 실은 경우는 1곳).
   - 유료·차단 페이지(Bloomberg, WSJ, FT 등)는 본문을 못 가져와 검증에 실패하니 피한다. 각 페이지를 WebFetch로 열어 본문과 게시 시각을 확인한다.
   - 카드의 각 장은 어느 기사에서 왔는지 claims로 연결되니, 기사마다 맡는 각도가 분명하게.
5) 원고 작성 — 저장소 tests/sample_post.json 과 같은 형식. 규칙:
   - 사실(숫자·날짜·기관·인물·발표 내용)은 연 출처 본문에 있는 것만. 숫자는 원문 표기 그대로.
   - cover_kicker 10자, cover_title 두 줄(\n, 줄마다 11자 이내), cover_subtitle 28자, slides 3~4장(heading 16자, highlight 10자 또는 "", points 1~3개 각 32자·가장 중요한 단어 하나만 **굵게**, terms 0~2개 {term 12자, meaning 32자}), takeaways 2~3개(24자), question 40자, caption 300자(첫 줄 핵심 사실, 이모지·느낌표·해시태그·출처 금지), hashtags 최대 8개(# 없이, 첫 번째 "AGI시대경제"), needs_disclaimer(특정 기업·종목·코인·금융상품이 나오거나 투자 판단으로 오해될 수 있으면 true).
   - 말투: 차분한 해설 기사 톤의 해요체. 전문용어는 points에서 풀지 말고 terms에. 마지막 본문 카드는 독자에게 미치는 영향·확인할 점.
   - claims: 카드·캡션의 모든 사실마다 {claim, source(아래 sources 배열의 1부터 번호), evidence(그 페이지 본문에서 글자 그대로 복사한 15~150자 구절)}.
6) 이슈 만들기: 아래 JSON을 본문 ```json 블록에 넣어
   `gh issue create -R dsh052617-lab/insta-autopost2 --title "직접: [M/D {LABEL}] <cover_title 한 줄>" --body-file <파일>`
   {"mode":"scheduled","date":POST_DATE,"topic":TOPIC,"category":"<분야>","reason":"<왜 골랐는지 한두 문장>","angle":"<관점 한 문장>","sources":["<출처 URL>", ...],"post":{...원고...}}
   category는 ai면 기술·모델/산업·기업/정책·규제/일자리·교육/생활·서비스/안전·윤리/반도체·인프라, economy면 금리·통화/물가·생활비/부동산·주거/금융·투자제도/고용·소득/무역·환율/재정·세금/산업·기업/글로벌 경제 중 하나.
7) 확인: 2분 뒤 `gh run list -R dsh052617-lab/insta-autopost2 --workflow manual.yml --limit 3`로 실행을 확인하고, 없으면 `gh workflow run manual.yml -R dsh052617-lab/insta-autopost2 -f issue=<번호>`. 최대 5분 동안 이슈 댓글을 확인해 "출처 검증을 통과하지 못했어요" 또는 "가져오지 못했어요"가 있으면, 문제 항목만 고친 원고로 새 이슈를 한 번 더 만들고 이전 이슈는 `gh issue close`로 닫는다(최대 1번).
8) 마지막 메시지 끝에 한 줄 덧붙인다: "📮 인스타 초안 · <cover_title 한 줄> · 승인: <이슈 링크> ({TIME} 게시 예정)". 검증 실패로 끝났으면 그 사실도 한 줄로.

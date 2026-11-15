# 픽스 예약 작업 — 인스타 기준으로 바꾸기 전 원래 지침 (되돌릴 때 사용)

## 픽스 · AI 산업 이슈 (trig_0126u3WY9pv3MyFpxKU4nYe2, 매일 10:00)
- 미국 중심: 3~5개 중 최소 3개(또는 2/3 이상)는 미국 매체·미국 기업/기관 발표. 한국 소식은 최대 1~2개.
- 미국 AI 기업 새 모델·제품 출시, 투자·인수·실적, 반도체·데이터센터, 미국 정부·규제 위주.
- 출처: 한 매체 최대 1개(불가피하면 2개). 공식 발표 → 통신사·경제지(AP, Reuters, Bloomberg, CNBC, Axios) → 기술 전문지(The Verge, Ars Technica, Wired, TechCrunch) 순.
- 24시간 이내(WebFetch로 게시 시각 확인), 허용 도메인 목록, 저장 전 매체 수 점검.
- 저장: ArtifactData news/ai {kind:"ai", title:"AI 산업 이슈", generatedAt, headline, items[{headline, summary, why, source, url, publishedAt}]}
- 메시지 첫 줄 "🤖 AI 이슈 · <가장 큰 소식 한 줄>", 항목마다 "🕒 … 게시 (KST) · 출처: 매체명 · 링크".

## 픽스 · 경제 시사 (trig_016Bf3J4VJ3LNKBG1DvMA87a, 매일 10:00)
- 지난 24시간 한국·글로벌 경제 뉴스 3~5개. 경제학 전공 대학생의 수업·금융권 취업 준비에 참고할 것 위주(금리, 환율, 물가, 고용, 정책, 주요 기업).
- 출처: 한국은행·기재부·금융위·금감원·통계청·KRX·Fed·BLS·기업 공식 발표, 주요 언론(연합·뉴시스·뉴스1·방송 3사·YTN·경제지·종합지·전자신문·ZDNet·Reuters·Bloomberg·AP·AFP·FT·WSJ·NYT·CNBC·Nikkei·The Verge·TechCrunch·Wired·Ars Technica). 공식 발표·통신사 우선.
- 저장: ArtifactData news/economy {kind:"economy", title:"경제 시사", …}
- 메시지 첫 줄 "📰 경제 시사 · <가장 큰 뉴스 한 줄>".

(전체 원문은 2026-11-15 대화 기록의 예약 작업 목록에 있음. 되돌리려면 Claude에게 "픽스 AI·경제 브리핑 지침을 예전으로 되돌려줘"라고 요청.)

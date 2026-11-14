# 수정 요청 정리 (인수인계 문서)

> 대상: 이 저장소(`insta-autopost`)를 이어서 수정할 개발자/AI
> 작성 시점: 2026-11-15 · 첫 자동 게시 목표: **2026-11-17(화) 20:00 KST**

## 0. 프로젝트 한 줄 요약

인스타그램 계정 **@agi.economy.kr**('AGI시대 경제')에 AI·경제 카드뉴스를 자동으로 올리는 프로그램이에요.
GitHub Actions에서 실행되고, 사람이 승인한 초안만 게시해요.
흐름: 신뢰 출처 RSS 수집 → Claude API가 이슈 선정·원고 작성 → 코드로 출처 검증 → Pillow로 카드 이미지(1080×1350) 생성 → GitHub 이슈로 검토 요청 → 댓글 `승인` → Instagram API로 캐러셀 게시

- 일정: 화 20:00 AI 1개, 목 20:00 경제 1개 (초안은 전날 20:23 생성)
- 내 주제: 이슈 제목을 `주제: …`로 쓰면 신뢰 출처 안에서 웹 검색해 같은 형식으로 생성
- 모델: 글쓰기 `claude-opus-5-5`, 내 주제 자료 검색 `claude-haiku-5-5`
- 시크릿: `ANTHROPIC_API_KEY`, `IG_ACCESS_TOKEN`(EAA… 통합 로그인 시스템 사용자 토큰), 선택 `IG_USER_ID`, 선택 `GH_PAT`

### 운영자가 정한 규칙 (바꾸면 안 됨)
1. **출처**: `config.yaml`의 `sources` 목록에 있는 도메인만 사용. 공식 발표 1건 이상, 또는 서로 다른 언론사 2곳 이상으로 교차 확인.
2. **검증 실패한 초안은 승인·게시 불가.** 사람이 승인해야만 게시돼요.
3. **최신 이슈만**: 자동 업로드는 최근 7일 기사만 써요. 기준은 '이번 주 가장 큰 이슈 + 취준생·국민에게 실질적 도움'이에요.
4. **새 AI 도구·제품 출시 소식은 최후의 선택**이에요. 다른 이슈가 없을 때만 골라요.
5. **카드 형식**: 요점은 짧게, 핵심 단어만 강조, 전문용어는 카드 하단에 한 줄 풀이, 이모지·느낌표·과장 금지.
6. **디자인**: 남색(#27466E, AI)·짙은 녹색(#2F5F50, 경제), 신뢰감 있고 광고 같지 않게.

---

## 1. [P0] 실제 환경에서 한 번도 실행해 보지 못한 부분 — 화요일 전에 꼭 확인

작성 환경이 외부 인터넷에 접속할 수 없어서, 아래 항목은 **모의 테스트(`tests/e2e_mock.py`)로만 확인했어요.** 실제로는 동작하지 않을 수 있어요.

### 1-1. Instagram 게시 (통합 로그인 / 시스템 사용자 토큰) — 가장 위험
- **배경:** Meta가 2026년 10월경 새 앱에서 'API setup with Instagram login'을 없애고 **'API setup with Unified login'만** 제공하기 시작했어요. 이 계정의 앱도 이 방식이에요.
- **현재 구현 (`src/instagram.py`):**
  - 토큰이 `IG`로 시작하면 `graph.instagram.com`, 아니면(EAA…) `graph.facebook.com/v26.0`으로 요청해요.
  - 캐러셀은 `/{ig-user-id}/media`(is_carousel_item) → `media_type=CAROUSEL` → `/media_publish` 순서예요.
- **확인할 것:**
  - [ ] 시스템 사용자 토큰(EAA)으로 `graph.facebook.com/{ig-user-id}/media` 게시가 되는지
  - [ ] `my_user_id()`의 계정 자동 찾기(`me/assigned_instagram_accounts` → `me/accounts?fields=instagram_business_account`)가 맞는지 → 안 되면 `IG_USER_ID` 시크릿으로 직접 넣는 방식으로 정리
  - [ ] 필요한 권한이 `instagram_basic` + `instagram_content_publish`로 충분한지 (`business_management` 필요 여부)
  - [ ] `is_ai_generated=true` 파라미터가 graph.facebook.com 경로에서 받아들여지는지 (거부되면 라벨 없이 재시도하는 코드는 있음)
  - [ ] README 4단계(비즈니스 포트폴리오 → 비즈니스 설정에 인스타 연결 → 시스템 사용자 → 자산 할당 → 토큰 생성)가 현재 Meta 화면과 맞는지

### 1-2. Instagram이 GitHub raw 이미지 주소를 받아가는지
- 이미지는 저장소에 커밋한 뒤 `https://raw.githubusercontent.com/{repo}/main/drafts/...jpg` 주소로 넘겨요 (`common.raw_url`).
- [ ] 실제 컨테이너 생성이 성공하는지 확인. 실패하면 GitHub Pages나 다른 공개 호스팅으로 바꾸고 `raw_url()`만 수정하면 돼요.
- 저장소는 **Public**이어야 해요 (Private이면 raw 주소가 열리지 않음).

### 1-3. RSS 피드 주소와 본문 수집 (`config.yaml` → `topics.*.feeds`, `src/news.py`)
- [ ] 각 피드가 GitHub Actions 러너에서 실제로 열리는지. 특히 확인이 필요한 곳:
  - 연합뉴스 `rss/industry.xml`, `rss/market.xml`, `rss/economy.xml`
  - 한국은행 `bbs/P0000093`, `P0002353`, `P0002017` RSS
  - `research.google/blog/rss/`, `news.microsoft.com/source/topics/ai/feed/`, MIT Tech Review AI 피드
- [ ] `trafilatura`가 본문을 400자 이상 뽑는지. **한국은행 게시물은 본문이 PDF/HWP 첨부라서 대부분 '본문 부족'으로 빠질 가능성이 커요** → PDF 첨부 텍스트를 추출하는 기능을 추가하는 게 좋아요(pdfplumber 등).
- [ ] 연합뉴스 등이 GitHub 러너 IP나 봇 User-Agent를 막는지 (403이면 대안 피드 필요)
- 참고: 정부 정책브리핑(korea.kr)은 2026년 7월 RSS 서비스를 중단해서 피드에서 뺐어요(도메인은 신뢰 출처 목록에 남아 있음).
- [ ] 국내 언론 피드(한경·매경·조선·동아·경향·한겨레·뉴시스)는 주소 확인 전으로 추가돼 있어요. 실패하는 피드는 고치거나 빼야 해요.
- [ ] **출처 자동 보충(`writer.corroborate`)**: 교차 확인이 부족하면 Haiku + web_search(allowed_domains=신뢰 출처)로 같은 사건 기사를 찾아 보충해요. 실제 검색 품질(같은 '사건'인지)과 비용을 확인해야 해요.
- [ ] 통신사 전재 감지(`news.wire_origin`)는 기사 앞부분의 `(서울=연합뉴스)`·`[세종=뉴시스]`·`(서울=뉴스1)` 패턴만 봐요. 다른 표기는 놓칠 수 있어요.

### 1-4. GitHub Actions 워크플로 실제 실행
- [ ] `draft.yml`, `publish.yml`, `comment.yml`, `custom.yml`, `refresh-token.yml`이 실제 저장소에서 문제없이 도는지
- [ ] `fonts-noto-cjk` 설치 뒤 `render._find_ttc()`가 한글 폰트를 찾는지
- [ ] `GITHUB_TOKEN`으로 git push가 되는지, 여러 워크플로가 동시에 push할 때 `pull --rebase` 재시도가 잘 되는지
- [ ] `comment.yml`의 조건(`draft` 라벨 + OWNER/MEMBER/COLLABORATOR)이 의도대로 동작하는지
- [ ] cron 시간 확인: 초안 `23 11 * * 1,3`(월·수 20:23 KST), 게시 `35 10 * * 2,4`(화·목 19:35 시작 → 20:00까지 대기)

### 1-5. Claude API 실제 응답
- [ ] 강제 도구 호출(tool_choice)로 받은 JSON이 스키마(글자 수, 요점 개수, terms, claims)를 잘 지키는지
- [ ] **claims의 evidence가 원문과 글자 그대로 일치하는 비율** — 낮으면 자동 재작성이 자주 일어나 비용이 늘고 검증 실패가 잦아져요
- [ ] 내 주제: `web_search_20250305` + `allowed_domains`가 Haiku 5.5에서 동작하는지, Console 조직 설정에서 웹 검색이 켜져 있어야 하는지, `pause_turn` 처리

---

## 2. [P1] 알려진 약점 — 동작은 하지만 고치면 좋은 부분

1. **숫자 검증의 오탐/누락** (`src/verify.py`)
   - 원문이 영어면 '3분기'↔'third quarter', '1조2천억'↔'1.2 trillion'처럼 표기가 달라 **정상 글이 실패할 수 있어요.**
   - 반대로 한 자리 숫자는 검사하지 않아요.
   - 개선안: 숫자·단위 정규화, 또는 Claude에게 원문 표기를 그대로 쓰게 더 강하게 지시.
2. **의미 검증 없음:** 코드는 '근거 구절이 원문에 있는가'와 '숫자'만 확인해요. 카드 문장이 원문 뜻을 왜곡했는지는 못 봐요.
   - 개선안: 별도 Claude 호출로 '카드 문장 ↔ 근거 구절' 일치를 판정하는 2차 검증.
3. **claims 누락:** Claude가 일부 사실의 근거를 빠뜨려도 잡지 못해요.
   - 개선안: 카드 요점마다 claim을 1개 이상 연결하게 스키마 변경(`points[].claim_ids`).
4. **본문 수집 실패 시 대안 없음:** 공식 발표 PDF를 못 읽으면 교차 확인 조건을 못 채워 초안이 안 만들어질 수 있어요(→ '초안 없음' 이슈 생성). 1-3의 PDF 추출과 연결된 문제예요.
5. **내 주제의 최신성 미검사:** 웹 검색으로 찾은 페이지의 날짜를 확인하지 않아요. 오래된 자료를 쓸 수 있어요.
6. **초안 생성 실패 알림 부족:** Claude 크레딧 소진 같은 오류로 초안 생성이 실패하면 GitHub 실행 실패 메일만 와요.
   - 개선안: 실패 시 이슈로 남기기(게시 실패는 이미 이슈 댓글로 남김).
7. **설정과 cron이 따로 놀아요:** `config.yaml`의 `post_time`·`days`를 바꾸면 워크플로 cron도 손으로 고쳐야 해요.
8. **이미지 대체 텍스트 없음:** Instagram API의 `alt_text`(이미지 컨테이너 파라미터)를 넣으면 접근성이 좋아져요. 카드 요점을 alt_text로 넣으면 돼요.
9. **선정 기준 일부만 코드로 강제돼요:** 분야 반복(최근 분야, 일자리↔고용 계열)은 코드가 막지만, 'AI 도구는 최후의 선택', '자극적 기사 제외'는 프롬프트 지시뿐이에요. 분야 분류도 Claude가 정해요.
10. **렌더링 넘침:** Claude가 글자 수 제한을 크게 넘기면 글자가 최소 크기까지 줄어도 넘칠 수 있어요. 하드 자르기(…)나 재작성 요청이 없어요.

## 3. [P2] 운영·유지보수

1. **공개 저장소라 초안이 승인 전에도 공개돼요.** `drafts/`의 이미지·post.json(근거 구절 포함)이 누구나 볼 수 있어요. 근거 구절은 짧지만 기사 원문 일부예요.
2. **저장소 용량:** 이미지가 쌓여 연 150MB 정도 늘어나요. 게시 후 오래된 초안을 정리하는 작업이 있으면 좋아요.
3. **history 범위:** 게시된 것만 기록해서, 건너뛴 이야기가 다음 주에 다시 뽑힐 수 있어요.
4. **테스트:** `tests/e2e_mock.py`는 모의 테스트 하나뿐이에요. 단위 테스트(verify, news._base_domain, render 넘침)가 있으면 좋아요.
5. **README의 Meta 화면 안내**는 Meta UI가 자주 바뀌어 금방 틀려질 수 있어요.

---

## 4. 파일 지도

| 파일 | 역할 |
|---|---|
| `config.yaml` | 계정, 일정, 모델, 신뢰 출처(`sources`), 피드, 색상 |
| `src/draft.py` | 정기 초안 생성 + 이슈 본문·캡션 만들기 (`build_caption`, `issue_body`) |
| `src/custom.py` | 내 주제 초안 (`주제:` 이슈 또는 수동 실행) |
| `src/news.py` | 피드 수집, 도메인 신뢰 판정(`_base_domain`, `source_info`), 본문 추출 |
| `src/writer.py` | Claude 프롬프트·스키마(`SELECT_TOOL`, `POST_TOOL`, `PICK_TOOL`), 검증 재작성 루프(`write_verified`) |
| `src/verify.py` | 출처 규칙, 근거 구절 대조, 숫자 대조 |
| `src/render.py` | 카드 디자인(표지/본문+용어풀이/한 줄 정리+출처) |
| `src/handle_comment.py` | 댓글 명령(승인/수정/지금 게시/취소) |
| `src/publish.py` | 예정 시각 게시, 실패 시 이슈 댓글, 지난 초안 정리 |
| `src/instagram.py` | Instagram API (토큰 종류별 host 분기) |
| `src/github_api.py` | 이슈·라벨·댓글, 이슈 본문 속 숨김 마커(`<!-- insta-draft: {...} -->`) |
| `.github/workflows/*.yml` | 1 초안 · 2 게시 · 3 댓글 처리 · 4 토큰 연장 · 5 내 주제 |
| `tests/e2e_mock.py` | 외부 접속 없이 전체 흐름 시험 |

## 5. 바로 시험해 보는 방법

```bash
pip install -r requirements.txt   # 한글 폰트: sudo apt-get install fonts-noto-cjk
python tests/e2e_mock.py          # 모의 전체 흐름 (끝나면 drafts/·data/history.json 원복)
ANTHROPIC_API_KEY=... python src/draft.py --local --topic economy   # 실제 뉴스+Claude로 미리보기만 (preview/ 폴더)
```

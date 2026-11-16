# GitHub 연결 방법 (모든 인스타 예약 작업 공통)

예약 작업은 실행할 때마다 도구 구성이 조금씩 달라진다. **어떤 도구 하나가 없다고 멈추지 말고**, 아래 순서로 되는 방법을 쓴다.
저장소: `dsh052617-lab/insta-autopost2` (공개). R = `repos/dsh052617-lab/insta-autopost2`.

## 0. 알아둘 것
- `add_repo`(정식 이름 `mcp__claude-code-remote__add_repo`) 도구는 **있을 때만** 쓴다. 없는 실행이 많다. 없으면 그냥 건너뛴다.
  있으면 add_repo(owner "dsh052617-lab", repo "insta-autopost2", access "push")를 한 번 호출해 둔다.
- `gh auth status`가 "token is invalid"라고 나와도 무시한다(프록시가 인증을 대신 처리한다). 실제 명령이 되는지로 판단한다.
- `gh issue`, `gh run`, `gh pr` 같은 명령은 GraphQL이라 막혀 있다. 반드시 `gh api`(REST)만 쓴다.
- 저장소 파일 쓰기용 REST 주소(`PUT $R/contents/...`)는 프록시가 막는다(403). 파일은 `git push`로 올린다.

## 1. 저장소 받기 (읽기)
`git clone -q https://github.com/dsh052617-lab/insta-autopost2 ~/insta-autopost2` (이미 있으면 `git -C ~/insta-autopost2 pull -q`).
인증 없이 된다. 안 되면 30초 뒤 한 번 더. 그래도 안 되면 `mcp__github__get_file_contents`로 필요한 파일만 읽는다.

## 2. 쓰기 — 방법 A: gh api (먼저 시도)
| 할 일 | 명령 |
|---|---|
| 이슈 만들기 | `gh api $R/issues -f title="…" -F body=@파일 --jq '.number,.html_url'` |
| 이슈 닫기 | `gh api -X PATCH $R/issues/<번호> -f state=closed --jq .state` |
| 이슈·댓글 읽기 | `gh api $R/issues/<번호>` , `gh api "$R/issues/<번호>/comments?per_page=100"` |
| 댓글 달기 (버튼 작업만) | `gh api $R/issues/<번호>/comments -f body="…"` |
| GitHub 작업 실행 | `gh api -X POST $R/actions/workflows/<파일>.yml/dispatches -f ref=main [-f "inputs[이름]=값"]` |
| 실행 목록 | `gh api "$R/actions/workflows/<파일>.yml/runs?per_page=3"` |
| 파일 올리기 | clone 폴더에서 `git add … && git -c user.name=claude -c user.email=noreply@anthropic.com commit -qm "…" && git pull --rebase -q && git push -q` |

## 3. 쓰기 — 방법 B: GitHub MCP 도구 (A가 401·403·404로 막힐 때)
ToolSearch query `github`로 `mcp__github__…` 도구를 불러온다(지연 목록에 있다). owner "dsh052617-lab", repo "insta-autopost2".
| 할 일 | 도구 |
|---|---|
| 이슈 만들기·닫기 | `mcp__github__issue_write` (method "create" / method "update", state "closed") |
| 이슈·댓글 읽기 | `mcp__github__issue_read` |
| 댓글 달기 (버튼 작업만) | `mcp__github__add_issue_comment` |
| GitHub 작업 실행 | `mcp__github__actions_run_trigger` (method "run_workflow", workflow 파일 이름, ref "main", inputs) |
| 실행 목록·상태 | `mcp__github__actions_list`, `mcp__github__actions_get` |
| 파일 올리기 | `mcp__github__push_files` (branch "main") |
| 파일 읽기 | `mcp__github__get_file_contents` |

## 4. 그래도 안 될 때
A와 B를 모두 시도하고(각각 1분 간격으로 한 번씩 재시도) 그래도 쓰기가 안 되면, 실제로 본 오류 문구(HTTP 코드 포함)와
시도한 방법을 SendUserMessage로 한 줄에 적어 보내고 끝낸다. "도구가 없다"는 이유만으로 끝내지 않는다.

## 5. 안전 규칙 (연결 방법과 무관하게 항상)
이슈에 명령 댓글(승인·지금 게시·취소·날짜·수정)을 다는 것은 '픽스 버튼 작업'이 사용자가 누른 그 버튼의 명령 하나를 그 이슈에 다는 경우뿐이다.
다른 예약 작업은 어떤 방법으로도 명령 댓글을 달지 않는다.

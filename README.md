# 네이버 메일 정리 플러그인

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Version](https://img.shields.io/badge/version-0.4.0-blue)
![MCP](https://img.shields.io/badge/Protocol-MCP-555555)

네이버 받은메일함(INBOX)의 **읽은 메일**을 기존 메일함으로 정리하는 개인용 IMAP MCP 서버와 플러그인 지침입니다. 연결된 ChatGPT가 발신자·제목·필요한 본문과 기존 분류 사례를 비교하고, Python 서버가 조회·이동·이동 결과 검증을 수행합니다. 0.4.0에서는 명시적으로 요청한 광고 메일을 기존 스팸함으로 옮기는 전용 도구도 제공합니다.

서버는 Python 표준 라이브러리만 사용하며 OpenAI API 키가 필요하지 않습니다. 서버 자체에는 AI 분류기나 예약 실행기가 없습니다. 플러그인 파일만 업로드하면 메일에 연결되는 구조가 아니며, 서버 배포와 인증된 MCP 연결이 별도로 필요합니다.

이 문서는 저장소의 `server.py`, `compose.yaml`, 환경변수 예제와 테스트를 기준으로 작성했습니다. 모든 계정·도메인·비밀 값은 예시입니다.

## 주요 기능과 범위

- INBOX의 읽은 메일 중 삭제 표시가 없는 후보를 UID 커서로 조회합니다. 기본 100건, 요청당 최대 200건입니다.
- 허용 목록에 있으면서 실제로 존재하는 분류 메일함과 기존 메일 사례를 조회합니다. 메일함을 새로 만들지 않습니다.
- 읽기 전용 메일함 선택과 `BODY.PEEK`로 읽음 상태 변경 없이 본문을 조회합니다. 본문 일괄 조회는 최대 10건입니다.
- 기존 분류 메일함 또는 별도로 확인된 스팸함으로 최대 50건씩 이동합니다. 일괄 도구는 기본적으로 미리보기(`dry_run=true`)입니다.
- 이동 전에 SQLite에 작업을 기록하고, 이동 후 원본 부재·목적지 메시지 동일성·읽음(`\Seen`)·별표(`\Flagged`) 보존을 검증합니다.
- 응답 유실이나 연결 단절이 발생한 작업은 이력을 조회하고 재검증합니다. 같은 작업을 다시 요청해도 자동으로 재이동하지 않습니다.

메일 발송, 독립적인 삭제·EXPUNGE, COPY 후 삭제 우회, 메일함 생성·변경·삭제, 플래그 수정, 스팸 신고, 발신자 차단, 구독 해지는 제공하지 않습니다. 이동에는 IMAP `UID MOVE` 지원이 필요합니다. 네이버 고유 중요 표시와 IMAP 별표의 대응은 실계정에서 별도로 확인해야 합니다.

## 구성과 파일

```text
ChatGPT / MCP 클라이언트
    │ HTTPS + Bearer 토큰
    ▼
Cloudflare Tunnel → cloudflared
    │ Docker 내부 HTTP: naver-mail-organizer:8080
    ▼
Python MCP 서버 ── TLS → imap.naver.com:993
    └─ SQLite: /data/audit.sqlite3 (mail-data 볼륨)
```

메일 제목·본문 등 도구가 반환하는 정보는 Cloudflare를 거쳐 연결된 클라이언트로 전달됩니다. 서버가 NAS에 있어도 모든 데이터 처리가 NAS 안에서 끝나는 것은 아닙니다. SQLite에는 계정·UID·목적지·검증용 지문·플래그·작업 이력이 저장되며, 본문 전문은 저장하지 않습니다.

```text
.
├─ README.md
├─ result/                              # 정리 전·후 참고 이미지
└─ naver-mail-organizer/                 # 배포 및 명령 실행 디렉터리
   ├─ plugin.json                       # 플러그인 메타데이터 (0.4.0)
   ├─ compose.yaml                      # 서버 + 선택적 Cloudflare Tunnel
   ├─ server.env.example                # IMAP·인증·이동 설정 양식
   ├─ tunnel.env.example                # Tunnel 토큰 양식
   ├─ SYNOLOGY_SETUP.md                 # NAS 설치 참고 안내
   ├─ server/
   │  ├─ Dockerfile                     # Python 3.12-slim, UID 10001
   │  ├─ server.py                      # HTTP JSON-RPC / IMAP / SQLite
   │  ├─ probe.py                       # 읽기 전용 진단 도구
   │  └─ configure_endpoint.py          # 원격 확인 후 mcp.json 생성
   ├─ skills/organize-read-mail/
   │  ├─ SKILL.md                       # 일반 분류·스팸 이동 절차
   │  └─ references/scheduled-prompt.txt # 일반 분류 예약용 지침
   └─ tests/
      ├─ test_server.py                 # 모의 IMAP 테스트
      └─ test_http.py                   # 로컬 HTTP 테스트
```

소스를 수정했다면 배포에는 위 디렉터리의 파일을 사용하세요. 저장소의 ZIP이 수정된 소스와 자동 동기화되지는 않습니다. [Synology 설치 참고 안내](naver-mail-organizer/SYNOLOGY_SETUP.md)는 0.3.0 설명이 남아 있으므로 버전·도구 수·스팸 설정은 이 README와 현재 코드를 기준으로 확인하세요.

## 설치와 첫 실행

Docker Compose를 사용할 수 있는 호스트가 필요합니다. 네이버 계정은 IMAP 사용을 활성화하고 앱 비밀번호를 준비합니다. 분류 목적지는 네이버 메일에 미리 존재해야 합니다. NAS에서는 네이버 IMAP(TCP 993)과 사용할 Tunnel의 외부 연결이 가능해야 합니다.

아래 배포 명령은 **NAS SSH 또는 Linux/Bash 기준**이며, 저장소 루트에서 내부 배포 디렉터리로 이동해 실행합니다. Docker 권한이 필요한 환경에서는 `sudo docker ...`를 사용하세요.

### 1. 환경 파일 준비

```bash
cd naver-mail-organizer
cp server.env.example server.env
cp tunnel.env.example tunnel.env
chmod 600 server.env tunnel.env
```

Tunnel을 아직 사용하지 않아도 두 파일을 준비합니다. `cloudflared`는 기본 실행에서 제외되지만 Compose가 환경 파일을 확인할 수 있습니다.

`server.env`를 편집합니다.

```dotenv
NAVER_USER=REPLACE_WITH_NAVER_ID
NAVER_APP_PASSWORD=REPLACE_WITH_APP_PASSWORD
NAVER_CLASSIFICATION_FOLDERS='["보안·계정","결제·금융","학업·교육","업무·취업","개발·서비스","여행·예약","소셜·개인","공지·뉴스레터"]'
NAVER_HANDLE_KEY=REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARACTERS
MCP_API_TOKEN=REPLACE_WITH_ANOTHER_RANDOM_SECRET_AT_LEAST_32_CHARACTERS
NAVER_ALLOW_MOVE=false
NAVER_MAX_MESSAGE_BYTES=5242880
NAVER_ALLOW_SPAM_MOVE=false
NAVER_SPAM_FOLDER=
```

`NAVER_CLASSIFICATION_FOLDERS`는 **실제 메일함 이름과 정확히 일치하는 JSON 문자열 배열**이어야 합니다. 위 이름은 예제 파일의 기본값이며 자동 생성되지 않습니다. 예를 들어 실제 이름이 `쇼핑·예약`이면 `여행·예약`을 그대로 두지 말고 실제 이름으로 바꿉니다. 시스템 메일함과 스팸함은 일반 분류 목적지에서 제외됩니다.

키와 토큰은 다음 명령을 **각각 실행해 서로 다른 값**을 생성합니다. 서버는 두 값이 32자 미만이거나 `REPLACE_`로 시작하면 기동을 거부합니다.

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

비밀 값에 `$`, `#` 등이 있으면 Compose 해석을 피하도록 값 전체를 작은따옴표로 감싸세요. 설정 파일·키·토큰은 공유하지 않습니다. 내부 `.gitignore`는 `server.env`, `tunnel.env`, `.env`, SQLite 파일, 생성된 `mcp.json` 등을 제외합니다.

### 2. 서버 실행과 연결 진단

```bash
docker compose up -d --build naver-mail-organizer
docker compose ps
docker compose exec -T naver-mail-organizer python /app/probe.py tools
docker compose exec -T naver-mail-organizer python /app/probe.py status
```

확인할 항목:

| 항목 | 기대 결과 |
| --- | --- |
| `tools` | 현재 11개 MCP 도구가 노출됨. 이 호출만으로 IMAP 연결을 검사하지 않음 |
| `server_version` | `0.4.0` |
| `connected` | `true` |
| `classification_folders` | 실제 사용할 기존 분류 메일함 목록 |
| `move_enabled` | 최초에는 `false` |
| `uid_move_supported` | 실제 이동을 위해 `true` 필요 |
| `post_move_verification`, `durable_move_journal` | `true` |

호스트의 프로세스 상태만 확인하려면 `curl http://127.0.0.1:18080/healthz`를 사용합니다. Compose는 호스트의 **루프백 주소 18080**에만 포트를 바인딩합니다. NAS에서 실행 중이면 이 주소도 NAS 내부에서 호출해야 합니다. 컨테이너의 Healthy 상태는 HTTP 프로세스 상태이며 IMAP 로그인 성공을 뜻하지 않습니다.

## 환경변수

| 변수 | 기본값 / 필수 여부 | 의미 |
| --- | --- | --- |
| `NAVER_USER` | 필수 | 네이버 IMAP 로그인 ID |
| `NAVER_APP_PASSWORD` | 필수 | 네이버 앱 비밀번호 |
| `NAVER_CLASSIFICATION_FOLDERS` | 필수 | 기존 일반 분류 메일함 허용 목록. JSON 배열 |
| `NAVER_HANDLE_KEY` | 필수, 32자 이상 | 메시지 핸들의 HMAC 서명 키 |
| `MCP_API_TOKEN` | 필수, 32자 이상 | `/mcp`의 Bearer 인증 토큰 |
| `NAVER_ALLOW_MOVE` | 미설정 시 비활성 | 정확히 `true`일 때 실제 이동 허용 |
| `NAVER_MAX_MESSAGE_BYTES` | `5242880` | 본문 다운로드 전 검사하는 메시지 전체 크기 한도(5 MiB) |
| `NAVER_ALLOW_SPAM_MOVE` | 미설정 시 비활성 | 정확히 `true`일 때 스팸 이동 추가 허용. 일반 이동 권한도 필요 |
| `NAVER_SPAM_FOLDER` | 빈 값 | 비워 두면 선택 가능한 `\Junk` 메일함이 정확히 하나일 때 자동 확인. 그 외에는 실제 IMAP 이름 지정 |
| `NAVER_AUDIT_DB` | Docker: `/data/audit.sqlite3` | 로컬 실행 기본값은 `./data/audit.sqlite3` |
| `MCP_BIND` | Docker: `0.0.0.0` | 로컬 실행 기본값은 `127.0.0.1` |
| `PORT` | `8080` | 서버 HTTP 포트 |
| `TUNNEL_TOKEN` | Tunnel 실행 시 필수 | `tunnel.env`에 설정하는 Cloudflare Tunnel 토큰 |

본문은 일반 텍스트를 우선 사용하고 없으면 HTML 태그를 제거한 텍스트를 반환하며, 반환 본문은 최대 20,000자입니다. 첨부파일을 별도로 분석하지 않습니다. 크기 초과 시 본문 조회는 실패하므로 분류 지침에 따라 보류합니다.

핸들은 계정·메일함·UID·UIDVALIDITY와 연결된 **서명된 참조이며 암호화된 값은 아닙니다**. 시간 기반 만료는 없지만 서명 키, 계정 또는 메일함 UIDVALIDITY가 바뀌면 기존 핸들을 사용할 수 없습니다.

## 외부 MCP 연결

`compose.yaml`의 `tunnel` 프로필을 사용합니다. 발급받은 터널 토큰만 `tunnel.env`의 `TUNNEL_TOKEN`에 입력한 뒤 실행합니다.

```bash
docker compose --profile tunnel up -d
docker compose logs --tail=100 cloudflared
```

Tunnel의 원본 서비스는 **`http://naver-mail-organizer:8080`**, 클라이언트에서 사용할 MCP 주소는 예를 들어 **`https://mail-mcp.example.com/mcp`**입니다. `example.com`을 실제 도메인으로 바꿉니다. 원본에 `localhost`나 호스트 루프백 포트 `18080`을 넣지 않습니다.

서버의 HTTP 인터페이스:

| 요청 | 동작 |
| --- | --- |
| `GET /healthz` | 인증 없는 프로세스 상태 확인 |
| `GET /mcp` | `405`, `Allow: POST` |
| `POST /mcp` | `Authorization: Bearer <MCP_API_TOKEN>` 필수. JSON-RPC 요청·JSON 응답 |
| 그 외 경로 | `404` |

`initialize`, `server/discover`, `ping`, `tools/list`, `tools/call`, 알림 요청을 처리합니다. SSE 스트림·OAuth·세션 저장 구현은 없습니다. 연결할 클라이언트에서 이 HTTP 방식과 Bearer 인증을 지원하는지 실제로 확인해야 합니다. Tunnel이 정상이어도 브라우저 로그인·Challenge가 개입하면 MCP 요청에 HTML이 반환될 수 있습니다.

패키지의 `mcp.json`이 필요하면 로컬 프로세스 환경에 `MCP_API_TOKEN`을 설정하고 **배포 디렉터리에서** 실행합니다.

```bash
python server/configure_endpoint.py
```

스크립트는 HTTPS 주소를 입력받아 실제 `tools/list`를 호출하고, 기대하는 도구가 있는지 확인한 뒤 배포 디렉터리에 `mcp.json`을 생성합니다. 토큰은 파일에 기록하지 않습니다. 이 검사는 IMAP 로그인·실제 이동·클라이언트 등록을 대신하지 않습니다. 현재 스크립트는 기존 10개 도구를 필수로 확인하므로 0.4.0 스팸 도구 노출은 별도로 확인하세요.

## 제공하는 MCP 도구

| 도구 | 역할 / 주요 인자 |
| --- | --- |
| `naver_status` | 연결, 서버 버전, 이동 권한, MOVE 지원, 분류함·스팸함 상태 |
| `naver_list_folders` | 실제 존재하는 허용된 일반 분류 메일함 목록 |
| `naver_list_read_inbox` | `limit` 기본 100·최대 200, `after_uid` 기본 0. 다음 요청에는 `next_after_uid` 사용 |
| `naver_sample_folder` | `folder`의 기존 메일 헤더 사례. `limit` 기본 3·최대 10 |
| `naver_read_message` | 서명된 `handle` 하나로 본문 조회 |
| `naver_read_messages` | `handles` 최대 10건. 건별 조회 결과·오류 반환 |
| `naver_move_read_inbox` | `handle`, `destination`으로 단건 **실제 이동**. 미리보기 인자 없음 |
| `naver_move_read_inbox_batch` | `items=[{"handle":"...","destination":"..."}]` 최대 50건. `dry_run` 기본 `true` |
| `naver_move_read_inbox_to_spam_batch` | `handles` 최대 50건, 서버가 확인한 스팸함으로만 이동. `dry_run` 기본 `true` |
| `naver_verify_moves` | 기존 작업의 `handles` 최대 50건 재검증. MOVE·플래그 변경 없음 |
| `naver_get_move_results` | `after_id` 기본 0, `limit` 기본 100·최대 200, `needs_attention` 기본 `false`. `has_more`, `next_after_id`로 페이지 조회 |

도구 결과는 JSON-RPC `result.content`의 텍스트 안에 JSON으로 반환됩니다. HTTP 200이어도 `result.isError=true`이면 도구 실행은 실패한 것입니다. 일괄 요청은 최상위 오류뿐 아니라 건별 결과도 확인해야 합니다.

## 분류와 실제 이동

1. `naver_status`, `naver_list_folders`를 호출하고 미확정 이동 이력을 먼저 확인합니다.
2. 기존 폴더별 사례를 읽어 분류 기준으로 사용합니다. 모델 재훈련은 수행하지 않습니다.
3. 읽은 INBOX 후보를 페이지별로 조회하고 필요할 때만 본문을 읽습니다. 제목만으로 목적이 불분명하거나 본문을 읽지 못하면 보류합니다.
4. 일괄 이동 도구의 `dry_run=true`로 목적지·후보를 먼저 확인합니다.
5. 실제 이동을 사용할 때 `server.env`의 `NAVER_ALLOW_MOVE=true`를 설정하고 컨테이너를 재생성합니다.

```bash
docker compose up -d --no-deps --force-recreate naver-mail-organizer
docker compose exec -T naver-mail-organizer python /app/probe.py status
```

단순 `restart`로는 변경한 `env_file` 값이 반영되지 않습니다. 소량의 별표 있는 메일과 없는 메일로 검증한 뒤 실제 이동을 요청합니다. 이동은 읽은 INBOX 후보 핸들만 받으며, 실행 직전에도 상태를 재확인합니다. 읽지 않은 메일은 이동 대상에서 제외합니다.

분류 지침의 기본 실행 범위는 최대 200건입니다. 전체 처리를 요청하면 반환 커서를 따라 끝까지 진행하고, 보류 때문에 첫 페이지를 반복하지 않습니다. 완료 시 남은 읽은 INBOX 후보를 다시 확인합니다.

### 광고 메일을 스팸함으로 이동

일반 분류와 별도 기능입니다. 사용자가 광고 메일의 스팸함 이동을 명시한 경우에만 적용합니다.

- `NAVER_ALLOW_MOVE=true`와 `NAVER_ALLOW_SPAM_MOVE=true`가 모두 필요합니다.
- `naver_status`의 `spam_folder`, `spam_folder_error`, `spam_move_enabled`를 확인합니다. 자동 확인이 실패하면 `NAVER_SPAM_FOLDER`에 실제 기존 IMAP 메일함 이름을 넣고 재생성합니다.
- `naver_move_read_inbox_to_spam_batch`의 미리보기 후 실제 이동을 수행합니다. 이 도구는 목적지 인자를 받지 않습니다.
- 할인·쿠폰·판촉처럼 상업적 홍보가 주목적인 메일을 분류합니다. 영수증·결제·배송·예약·보안·업무 연락 등 필수 안내는 광고 문구가 일부 있어도 보호합니다. 판단이 불확실하면 보류합니다.

스팸함 이동은 스팸 신고나 차단이 아닙니다. 일반 분류 도구에 스팸함을 목적지로 넣어 우회하지 않습니다.

### 이동 결과와 복구

| 상태 | 의미와 처리 |
| --- | --- |
| `preview` | 미리보기. 실제 이동 성공에 포함하지 않음 |
| `verified` | 원본 부재·목적지 동일성·읽음·별표 검증 완료 |
| `pending`, `unresolved` | 미확정. 신규 이동을 멈추고 재검증 |
| `verification_failed` | 보존·동일성 등 검증 실패. 이동 중단 후 조사 |
| `legacy_unverified` | 이전 버전 이력에 검증 근거 부족. 성공으로 소급 집계하지 않음 |
| `rejected`, `not_attempted`, `not_recorded` | 거부·미시도·이력 없음. 성공에 포함하지 않음 |

이동 명령의 OK나 INBOX 건수 감소만으로 성공을 확정하지 않습니다. 신규 성공은 `newly_verified_count`와 건별 `newly_verified`를 사용하고 `operation_id`로 중복을 제거합니다. `verified_count`에는 기존 작업 재확인이 포함될 수 있으며 이력의 `totals`는 계정 전체 누적값입니다.

연결이 끊겼다면 읽기 전용 진단으로 주의가 필요한 이력을 복구합니다.

```bash
docker compose exec -T naver-mail-organizer python /app/probe.py history
```

`history` 모드는 주의가 필요한 이력의 첫 페이지를 조회합니다. 더 있으면 MCP 이력 도구로 페이지를 이어서 조회합니다. 핸들을 확보한 뒤 최대 50건씩 재검증합니다.

```bash
printf '%s\n' '{"handles":["REPLACE_WITH_RETURNED_HANDLE"]}' | docker compose exec -T naver-mail-organizer python /app/probe.py verify
```

`after_id`는 신규 작업 열거용이며 상태 변경 피드가 아닙니다. 복구할 때는 0부터 다시 조회합니다. 재검증은 MOVE를 재실행하거나 플래그를 자동 수정하지 않습니다. 미확정 작업을 무작정 재시도하지 마세요.

## 요청 예시와 예약

미리보기:

```text
네이버 메일 정리 도구로 연결 상태와 기존 분류함을 확인해줘.
읽은 받은메일함 메일 10건을 기존 사례와 비교하고 분류안과 근거를 보여줘.
실제 이동은 하지 말고 불명확한 메일은 보류해줘.
```

실제 일반 분류:

```text
네이버 받은메일함의 읽은 메일을 기존 분류함으로 정리해줘.
연결·권한·미확정 이력과 소량 이동 검증 결과를 먼저 확인해줘.
기본 범위 200건 안에서 근거가 충분한 메일만 이동하고,
새로 검증된 이동·보류·실패·미확정·남은 범위를 보고해줘.
```

스팸함 이동:

```text
읽은 받은메일함 중 상업적 광고가 주목적인 메일을 기존 스팸함으로 옮겨줘.
별도 스팸 이동 권한과 목적지를 확인하고 미리보기·소량 검증 후 진행해줘.
결제·배송·예약·보안·업무 안내는 보호하고, 애매하면 보류해줘.
```

서버에는 cron이나 예약 분류 루프가 없습니다. 예약은 별도 실행 환경에서 도구를 호출해야 하며, [예약용 지침](naver-mail-organizer/skills/organize-read-mail/references/scheduled-prompt.txt)은 일반 폴더 분류용입니다. 예약 환경의 도구 접근·인증·실제 읽기 호출과 소량 이동 검증을 확인해야 합니다. 서버나 Tunnel을 켜 두는 것만으로 매일 분류가 실행되지는 않습니다.

## 개발과 테스트

Python **3.11 이상**이 필요하며 Docker 이미지는 3.12를 사용합니다. 별도 `requirements.txt`나 pip 패키지 설치는 필요하지 않습니다. 저장소 루트에서:

```bash
python -m unittest discover -s naver-mail-organizer/tests -v
```

테스트는 모의 IMAP과 로컬 HTTP 서버를 사용합니다. 페이지 조회·본문 크기 제한·핸들 검증·일괄 이동·플래그 보존·작업 기록·응답 유실 후 재검증·스팸 권한·HTTP 인증 등을 검사하며 실제 네이버 메일은 이동하지 않습니다. 테스트 통과만으로 Docker 빌드, NAS 권한, Cloudflare 연결, 실제 네이버 동작, 클라이언트 호환성, 예약 실행이 검증되지는 않습니다.

Docker 없이 실행하려면 현재 프로세스에 필요한 환경변수를 설정한 뒤 실행합니다. `server.py`는 `server.env`를 자동으로 읽지 않습니다.

```bash
python naver-mail-organizer/server/server.py
```

## 운영과 문제 해결

배포 디렉터리에서 실행합니다.

```bash
# 서버 갱신 및 연결 확인
docker compose up -d --build naver-mail-organizer
docker compose exec -T naver-mail-organizer python /app/probe.py status

# 서버·터널 로그
docker compose logs --tail=100 naver-mail-organizer
docker compose logs --tail=100 cloudflared
```

이동을 중지하려면 `NAVER_ALLOW_MOVE=false`로 바꾼 뒤 서버를 재생성합니다. Tunnel 토큰 변경 후에는 `docker compose --profile tunnel up -d --no-deps --force-recreate cloudflared`를 실행합니다.

`mail-data` 볼륨은 재생성 후에도 유지해야 합니다. SQLite 백업은 서버 중지 상태 또는 SQLite의 일관된 백업 방법으로 수행합니다. `docker compose down -v`는 이력 볼륨을 삭제하므로 업데이트에 사용하지 않습니다. bind mount로 변경하면 컨테이너 UID 10001의 쓰기 권한을 확인합니다. `restart: unless-stopped`는 프로세스 종료 복구 설정이며 unhealthy 상태만으로 재시작하지 않습니다.

| 증상 | 확인·조치 |
| --- | --- |
| 설정 누락·random secret 오류 | 예시 값 교체, 필수 값·키 길이 확인 |
| Healthy인데 IMAP 실패 | `probe.py status`로 IMAP 사용 설정·로그인 ID·앱 비밀번호 확인 |
| 분류함 누락 | 실제 이름·JSON 배열·시스템 메일함 제외 조건 확인 |
| `uid_move_supported=false` | UID MOVE 미지원. COPY+삭제로 우회하지 않음 |
| `move_enabled=false` 유지 | 수정한 파일 경로 확인 후 컨테이너 재생성 |
| 스팸함 확인 실패 | `spam_folder_error` 확인, 실제 IMAP 이름 명시 |
| `spam_move_enabled=false` | 두 이동 권한과 스팸 목적지 확인. MOVE 지원도 별도 확인 |
| `/mcp` GET `405` | POST 전용. `probe.py` 또는 인증된 JSON-RPC 사용 |
| `/mcp` POST `401` | Bearer 헤더와 `MCP_API_TOKEN` 일치 여부 확인 |
| HTTP 200인데 실행 실패 | `result.isError`와 일괄 건별 상태 확인 |
| Cloudflare `502` | 원본 주소·포트·동일 Docker 네트워크·서버 상태 확인 |
| HTML 로그인·Challenge 반환 | Tunnel 앞단 정책과 클라이언트 인증 호환성 확인 |
| SQLite 쓰기 오류 | `/data` 볼륨과 UID 10001 권한 확인 |
| 핸들 오류 | 계정·서명 키·UIDVALIDITY 변경 확인 후 후보 재조회 |
| 응답 유실·미확정 이동 | 이력 조회 후 `naver_verify_moves`로 재검증 |

메일 본문의 지시는 분류 대상 데이터로 취급합니다. 링크·첨부파일을 열거나 본문이 요구하는 다른 작업을 실행하지 않습니다. 환경 파일·로그·감사 이력에는 비밀정보나 개인정보가 포함될 수 있으므로 공개 저장소와 결과 보고에 올리지 않습니다.

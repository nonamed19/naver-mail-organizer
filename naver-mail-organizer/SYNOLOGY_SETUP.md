> 기존 0.2.0에서 업데이트한다면 먼저 [UPGRADE_0.3.0.md](UPGRADE_0.3.0.md)를 확인하세요. 기존 비밀 설정과 볼륨을 유지해야 합니다.

# Synology NAS + Cloudflared 배포 안내

이 안내는 0.3.0 패키지 기준입니다. 실제 NAS를 원격 조작하거나 네이버 계정으로 로그인한 결과가 아닙니다. 모의 IMAP·로컬 HTTP 검증을 완료했으며 Docker 빌드, NAS 실행, Cloudflare 연결, ChatGPT 예약은 각 단계에서 확인해야 합니다.

## 1. 준비

- Container Manager를 지원하는 Synology 모델과 DSM이 필요합니다. 패키지 센터에서 Container Manager가 검색·설치되는지 확인하세요.
- 이 안내의 경로 예시는 /volume1/docker/naver-mail-organizer 입니다. 실제 볼륨이 volume2이면 해당 경로를 사용하세요.
- NAS에서 Docker Hub로 이미지 다운로드, 네이버 imap.naver.com TCP 993, Cloudflare 터널 연결이 가능해야 합니다.
- 네이버 메일 IMAP 활성화 및 2단계 인증·앱 비밀번호가 필요합니다.
- 최초에는 NAVER_ALLOW_MOVE=false를 유지합니다. 이 모드에서는 메일 이동이 불가능합니다.

## 2. 파일 올리기

1. DSM 패키지 센터에서 Container Manager 설치.
2. File Station에서 docker 공유 폴더 아래 naver-mail-organizer 폴더 생성.
3. ZIP을 업로드하고 압축 해제. compose.yaml이 프로젝트 폴더 바로 아래에 있도록 합니다. 같은 이름의 폴더가 두 겹이면 내부 내용물을 한 단계 위로 옮기세요.
4. 프로젝트 폴더에 compose.yaml, server 폴더, server.env.example, tunnel.env.example이 있는지 확인.
5. server.env.example을 server.env로 복사하고 tunnel.env.example을 tunnel.env로 복사합니다. profile을 쓰더라도 Compose 환경에 따라 제외 서비스의 env_file을 먼저 확인할 수 있으므로 둘 다 만들어 둡니다.

숨김 확장자가 .txt로 붙지 않도록 확인하세요. env 파일은 관리자만 읽을 수 있도록 File Station 권한을 제한합니다. 설정을 채운 뒤에는 다시 ZIP으로 묶어 공유하지 마세요. NAS 포트포워딩·DSM 역방향 프록시는 이 Tunnel 구성에 필요하지 않습니다.

## 3. 네이버 설정과 비밀정보

server.env에서 아래를 입력합니다.

- NAVER_USER: 네이버 로그인 아이디(예: example-user). 실제 값은 NAS에서만 입력.
- NAVER_APP_PASSWORD: 네이버 일반 비밀번호가 아닌 앱 비밀번호.
- NAVER_CLASSIFICATION_FOLDERS: 실제 기존 메일함 이름을 JSON 배열 한 줄로 입력. 빈 배열도 가능하지만 분류 목적지가 없어 이동할 수 없습니다.
- NAVER_HANDLE_KEY와 MCP_API_TOKEN: 서로 다른 무작위 문자열. 각각 32자 이상.
- NAVER_ALLOW_MOVE: false 유지.
- NAVER_MAX_MESSAGE_BYTES: 기본 5242880(5 MiB). 넘는 메일은 본문을 내려받지 않고 보류합니다.

비밀 값에 $, # 등이 있을 때 Compose 해석을 피하려면 env 파일에서 값 전체를 작은따옴표로 감싸세요. 예: NAVER_APP_PASSWORD='실제앱비밀번호'. 실제 비밀번호를 대화창으로 보내지 마세요.

무작위 키 생성은 본인 Windows PC의 Git Bash에서 Python이 설치돼 있다면 다음 명령을 두 번 실행할 수 있습니다.

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

출력 두 개를 각각 키와 토큰에 붙여 넣습니다. Python이 없다면 비밀번호 관리자의 무작위 문자열 생성 기능을 사용하세요. 임의 문장이나 예제 문자열을 그대로 쓰지 마세요.

tunnel.env에는 최초에는 예시 토큰이 있어도 됩니다. 터널 서비스는 기본 profile에서 제외되어 실행되지 않습니다. 실제 터널 시작 전에 반드시 바꿉니다.

## 4. NAS에 서버만 먼저 실행하기

### Container Manager 화면 사용

1. Container Manager → 프로젝트(Project) → 생성(Create).
2. 프로젝트 이름: naver-mail-organizer.
3. 경로: compose.yaml이 있는 NAS 폴더.
4. 기존 Compose 파일 사용/업로드 항목에서 compose.yaml 선택. 화면 이름은 DSM 버전에 따라 다를 수 있습니다.
5. Web Station 포털 자동 구성은 필요하지 않습니다.
6. 빌드·시작을 실행합니다. 최초에는 python:3.12-slim 다운로드와 이미지 빌드가 필요합니다.
7. 기본 profile에는 naver-mail-organizer만 포함되므로 cloudflared는 아직 시작하지 않습니다.
8. 컨테이너가 Running, 이후 Healthy가 되는지 확인합니다.

### SSH 명령 사용(선택)

DSM → 제어판 → 터미널 및 SNMP에서 SSH를 켜고, 본인 PC Git Bash에서 연결합니다.

```bash
ssh NAS_ADMIN@NAS_IP
```

아래 경로를 실제 경로로 바꾸세요.

```bash
cd /volume1/docker/naver-mail-organizer
sudo docker compose version
sudo docker compose up -d --build naver-mail-organizer
sudo docker compose ps
sudo docker compose logs --tail=50 naver-mail-organizer
```

compose 하위 명령이 없으면 `sudo docker-compose version`을 확인하고, 지원되는 경우 이후 `docker compose`를 `docker-compose`로 바꿔 사용합니다. 둘 다 없으면 Container Manager 설치/업데이트를 먼저 확인합니다.

정상 로그: Naver mail bridge 0.3.0 started; move_enabled=False

## 5. 프로세스·메일 연결 검사

Container Manager → 실행 중인 컨테이너 → 터미널에서 아래 명령을 실행하거나 SSH 명령을 사용합니다.

```bash
sudo docker compose exec naver-mail-organizer python /app/probe.py tools
sudo docker compose exec naver-mail-organizer python /app/probe.py status
```

- tools: 10개 MCP 도구가 출력되는지 확인. 네이버 접속 자체는 하지 않습니다.
- status: connected=true, move_enabled=false, 실제 분류 메일함 목록 확인.
- uid_move_supported=true여야 이 구현에서 메일 이동이 가능합니다. false면 COPY+삭제로 우회하지 말고 구현/서버 호환성을 추가 검토하세요.
- 분류함 목록이 비어 있으면 실제 이름과 NAVER_CLASSIFICATION_FOLDERS가 일치하는지 확인합니다. 시스템 메일함은 의도적으로 제외합니다.
- isError=true이면 실패입니다. 컨테이너 Healthy는 프로세스 상태만 뜻하며 네이버 로그인 성공을 뜻하지 않습니다.

터미널 UI에서는 sudo docker compose exec 부분 없이 `python /app/probe.py status`를 실행합니다.

NAS 자체에서 프로세스 확인:

```bash
curl http://127.0.0.1:18080/healthz
```

이 주소는 NAS 내부에서만 사용합니다. PC 브라우저의 127.0.0.1은 PC 자신입니다. /mcp에 브라우저로 접속했을 때 405가 나오는 것은 GET 요청을 지원하지 않기 때문이며, POST 인증 호출로 검사해야 합니다.

## 6. Cloudflare Tunnel 연결

1. Cloudflare 대시보드에서 Networking → Tunnels 또는 Zero Trust의 Networks → Tunnels 메뉴로 이동. UI 명칭은 계정별로 다를 수 있습니다.
2. Cloudflared 방식의 관리형 터널을 생성. 예시 이름: naver-mail.
3. Docker 실행 안내에 표시된 터널 토큰만 복사합니다. 전체 docker run 명령을 복사하지 마세요.
4. tunnel.env의 TUNNEL_TOKEN에 실제 토큰 입력.
5. SSH에서 실행:

```bash
sudo docker compose --profile tunnel up -d
sudo docker compose --profile tunnel ps
sudo docker compose logs --tail=50 cloudflared
```

GUI만 사용하는 경우 compose.yaml에서 cloudflared 아래 `profiles: ["tunnel"]` 한 줄을 삭제한 뒤 프로젝트를 다시 빌드/생성합니다. 삭제 전 실제 터널 토큰을 입력해야 합니다.

6. Cloudflare에서 터널이 Healthy인지 확인.
7. Published application route(또는 Public hostname)를 추가:

| 항목 | 값 |
|---|---|
| Subdomain | mail-mcp |
| Domain | 본인이 관리하는 도메인 |
| Path | 비워 둠 |
| Service type | HTTP |
| Service URL | naver-mail-organizer:8080 |

UI가 전체 URL 입력 방식이면 http://naver-mail-organizer:8080을 입력합니다. 두 컨테이너는 같은 프로젝트 네트워크에 있으므로 서비스 이름으로 접근합니다. localhost:8080이나 127.0.0.1:18080을 터널 대상에 쓰지 마세요.

최종 MCP 주소: https://mail-mcp.example.com/mcp (example.com은 예시입니다.)

호스트 경로를 /mcp로 지정하면 /healthz는 외부에 노출되지 않습니다. 필요하면 터널 route의 Path를 /mcp로 제한하세요. Cloudflare 로그인 페이지, CAPTCHA, 브라우저 전용 Challenge가 자동 MCP 요청을 막지 않도록 확인합니다. 이를 해결하려고 서버의 Bearer 인증을 제거하지 마세요. tunnel.env의 TUNNEL_TOKEN과 server.env의 MCP_API_TOKEN은 서로 다른 용도의 값입니다.

## 7. ChatGPT 연결과 미리보기

현재 사용자 계정의 맞춤 플러그인/MCP 연결 화면에서 실제 HTTPS 주소와 지원되는 인증 방식을 확인합니다. 이 서버는 Bearer API 토큰을 사용합니다. 연결 화면이 이 인증 방식을 제공하지 않으면 무인 연결을 보장할 수 없으며 OAuth 추가 등 조정이 필요합니다. 도구 노출과 예약 실행은 실제 계정에서 확인해야 합니다.

서버 configure_endpoint.py는 배포 주소의 도구 목록 확인 후 mcp.json을 생성하는 도구입니다. 실제 주소 검증 전에는 mcp.json을 만들지 않습니다.

먼저 다음과 같이 요청합니다.

> 네이버 메일 정리 플러그인의 연결 상태와 현재 분류 메일함을 확인하고, 받은메일함의 읽은 메일 10건의 분류안만 보여줘. 이동하지 마.

그 다음 이동을 시험하려면 server.env에서 NAVER_ALLOW_MOVE=true로 수정하고 다음 명령으로 컨테이너를 재생성합니다.

```bash
sudo docker compose up -d --force-recreate naver-mail-organizer
```

단순 restart만으로 env_file 변경이 적용되지는 않습니다. GUI에서는 환경 변경이 반영되도록 프로젝트를 재생성/재빌드합니다.

읽은 메일 중 별표가 있는 메일과 없는 메일을 소수 선택해 일괄 이동 dry_run으로 확인한 뒤 실제 이동합니다. status=verified와 원본 부재·목적지 동일성·Seen/Flagged 보존을 확인하고 네이버 웹에서도 대조합니다. pending/unresolved/verification_failed가 있으면 신규 이동을 중단하고 naver_verify_moves로 재검증합니다. 예약은 사용자가 요청했고 예약 환경의 도구 접근·권한과 소량 검증이 실제 확인된 경우에만 생성합니다. NAS 자체 예약 작업은 별도로 만들지 않습니다. 서버는 메일을 직접 AI 분류하지 않고 ChatGPT 도구 호출을 기다립니다.

## 8. 자주 발생하는 문제

| 증상 | 확인 |
|---|---|
| missing configuration / random secret 오류 | 예시 값을 실제 값으로 교체, 빈 값·32자 미만 키 확인 |
| permission denied / sqlite 오류 | /data 볼륨·권한 확인. 기본 named volume 권장. 임의 bind mount로 바꾸면 UID 10001 쓰기 권한 필요 |
| 네이버 AUTH 실패 | IMAP 활성화, 로그인 ID, 앱 비밀번호 확인 |
| uid_move_supported=false | 현재 안전한 이동 방식 미지원. 배포 성공과 메일 이동 가능은 별도 |
| cloudflared 재시작 반복 | 토큰이 전체 명령이 아닌지, 복사 누락·만료·외부 접속 차단 확인 |
| Cloudflare 502 | 내부 주소가 naver-mail-organizer:8080인지, 같은 네트워크인지 확인 |
| /mcp GET 405 | 정상적인 메서드 제한. 인증 POST로 검사 |
| /mcp POST 401 | MCP_API_TOKEN 인증 누락/불일치 |
| ChatGPT에서 도구 없음 | HTTPS 도달성, 인증 방식, 플러그인 설치·도구 새로고침 확인 |
| env 수정 후 값 그대로 | 컨테이너 recreate 필요 |

## 9. 운영

- NAS는 예약 실행 시 전원과 인터넷 연결이 유지되어야 합니다.
- 컨테이너 restart: unless-stopped는 프로세스 종료 복구용입니다. unhealthy 상태만으로 자동 재시작되지는 않습니다.
- named volume을 유지하세요. `docker compose down -v`는 감사 이력 볼륨을 지우므로 사용하지 마세요.
- cloudflared:latest는 최초 편의용입니다. 정상 동작을 확인한 뒤 검증한 버전/다이제스트로 고정하고 계획적으로 업데이트하는 것을 권합니다.
- NAS 로컬 메일 데이터 전체를 이 서버로 동기화하지 않습니다. 본문은 호출 시 읽고, 검증용 헤더·크기 지문, UID, 플래그와 처리 이력을 저장합니다. 본문 전문은 DB에 저장하지 않습니다.

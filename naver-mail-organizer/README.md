# 네이버 메일 정리 플러그인 0.2.0

Synology NAS + Container Manager + Cloudflared 운영용 소스와 ChatGPT 분류 스킬입니다. 최초 ZIP 업로드만으로 메일 도구나 예약이 생기지는 않습니다. NAS 서버를 배포하고 실제 HTTPS MCP 연결을 추가해야 합니다.

배포는 **SYNOLOGY_SETUP.md**를 순서대로 따라 하세요. compose.yaml, server.env.example, tunnel.env.example, 서버 Dockerfile과 진단 도구가 포함되어 있습니다. 실제 인증정보나 개인 이름은 없습니다.

## 동작

- INBOX의 읽은 메일만 기존 분류용 메일함으로 이동합니다.
- 기존 분류 사례는 참고용으로만 읽으며 첨부파일은 분석하지 않습니다.
- 애매한 메일은 받은메일함에 둡니다.
- 메일 삭제·발송·폴더 생성/이름 변경/삭제 도구는 없습니다.
- 읽음/별표 플래그를 수정하는 명령을 보내지 않습니다. 네이버 고유 중요 표시의 보존은 실계정 확인이 필요합니다.
- UID MOVE를 지원하지 않으면 이동을 거부합니다. COPY+삭제로 우회하지 않습니다.
- 기본 preview 설정(NAVER_ALLOW_MOVE=false)에서는 이동할 수 없습니다.
- 본문 조회 전 원문 크기를 확인하고 기본 5 MiB 초과 메시지는 보류합니다. 분석 텍스트는 최대 20,000자입니다.
- 단일 계정·단일 소유자용입니다. 다중 사용자 서비스나 계정 간 공유 서버로 쓰지 마세요.

## 구성

plugin.json은 업로드용 메타데이터, skills는 분류 지침입니다. server는 Python 3.11+ 표준 라이브러리 기반의 IMAP MCP 서버입니다. compose.yaml은 NAS에서 메일 서버를 실행하며, tunnel profile을 켜면 Cloudflared도 실행합니다. 처리 이력은 /data의 SQLite에 저장합니다.

현재 실배포 주소가 없으므로 루트 mcp.json은 없습니다. server/configure_endpoint.py가 실제 HTTPS 주소의 tools/list를 검증한 뒤 비밀정보 없이 연결 설정을 생성합니다. 인증은 Bearer API 토큰이며 ChatGPT 계정에서 해당 연결/예약 쓰기 방식을 사용할 수 있는지 별도 검증해야 합니다. OpenAI API 호출은 구현하지 않았습니다.

## 검증 및 제한

로컬 자동 테스트와 HTTP 검사를 수행했습니다. 실제 Docker 이미지 빌드 및 NAS, 네이버 계정, Cloudflare, ChatGPT 예약의 통합 실행은 아직 수행하지 않았습니다. /healthz는 프로세스 상태만 나타내며 네이버 로그인 성공을 뜻하지 않습니다.

```bash
python -m unittest discover -s tests -v
```

상세 분류 지침: skills/organize-read-mail/SKILL.md
예약 지침: skills/organize-read-mail/references/scheduled-prompt.txt

공식 참고:
- https://help.naver.com/service/30029/contents/21344
- https://learn.chatgpt.com/docs/automations
- https://developers.cloudflare.com/tunnel/get-started/
- https://www.synology.com/ko-kr/dsm/feature/container-manager

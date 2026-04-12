# Discord 역할 지급 봇

Discord 슬래시 명령어로 멤버 정보를 JSON에 저장하고 역할을 자동 지급하는 봇.

## 구조

- `bot.py` — 봇 메인 코드 (슬래시 명령어 처리, JSON 저장, 역할 지급)
- `members.json` — 참여한 멤버 데이터 저장 (자동 생성)

## 슬래시 명령어

| 명령어 | 설명 | 권한 |
|--------|------|------|
| `/참여` | 멤버 참여 등록 + 역할 자동 지급 | 모든 멤버 |
| `/목록` | 참여 멤버 목록 확인 | 관리자 |
| `/역할일괄지급` | JSON 목록 전체 역할 지급 | 관리자 |

## 환경변수 (Secrets)

- `DISCORD_TOKEN` — Discord 봇 토큰
- `DISCORD_GUILD_ID` — 서버(길드) ID
- `ROLE_ID` — 지급할 역할 ID

## 실행

```bash
python bot.py
```

## 기술 스택

- Python 3.11
- discord.py

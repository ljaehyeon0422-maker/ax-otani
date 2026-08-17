# Yongsan IMAX Seat Watcher

개인용 **CGV 용산아이파크몰 IMAX 좌석 감시 + Discord 알림 봇**의 안전 우선 버전입니다.

## 현재 구현된 기능

- Discord `/setup` 대화형 기본 설정
  - 기본 관람 인원 1~8명
  - `명당만 / 좋은 자리 / 웬만하면 OK / 최대한 넓게`
  - `전원 연석 / 최소 2연석 / 연석 우선 / 상관없음`
- Discord `/watch_menu`
  - 연결된 좌석 피드에서 영화 선택 → 날짜 선택 → 기본 설정으로 감시
- `/watch`
  - 특정 영화·날짜만 인원/연석/좌석범위를 다르게 설정
- `/movie_override`
  - 영화별 기본값 덮어쓰기
- `/watches`, `/pause`, `/resume`
- 좌석 번호 하드코딩 대신 **실제 좌석맵의 상대 위치**로 선호 좌석 계산
  - `okay` 기본값은 너무 앞쪽과 극단 사이드를 제외하고 넓게 허용
- 연석 자동 판정
- 같은 좌석이 계속 비어 있을 때 중복 알림 방지
  - 좌석이 사라졌다가 다시 나타나면 재알림
- 요청 최소 30초 간격
- 429/오류 발생 시 지수 백오프
- 401/403 발생 시 우회하지 않고 감시 중지 + Discord 경고

## 중요한 현재 제한사항

2026년 현재 CGV의 최신 티켓 API는 자동화된 서버 요청에 대해 서명 헤더 및 접근 제한을 사용하고 있습니다. 이 프로젝트는 **서명키 추출, Cloudflare 우회, 프록시를 통한 차단 회피 같은 기능을 포함하지 않습니다.**

따라서 정확한 좌석번호(H23 등)를 실시간으로 가져오는 부분은 `CGV_FEED_URL`이라는 **허용된 JSON 좌석 피드 어댑터**로 분리했습니다. Discord/UI/좌석정책/연석/알림 엔진은 구현되어 있으며, 정상적으로 사용할 수 있는 좌석 데이터 경로를 연결하면 그대로 동작합니다.

이 설계는 CGV에 불필요한 요청을 보내거나 차단을 우회하는 것보다 계정/IP 패널티 가능성을 낮추는 것을 우선합니다. 패널티가 절대 없음을 보장할 수는 없습니다.

## 설정 우선순위

```text
사용자 기본값
   ↓
영화별 override
   ↓
해당 영화/날짜 watch override
```

가장 아래 단계가 우선합니다.

예시:

- 기본: 2명 / 연석 우선 / 웬만하면 OK
- 영화 A: 3명 / 전원 연석
- 영화 A, 8월 23일: 1명 / 좋은 자리

→ 8월 23일에는 마지막 조건이 적용됩니다.

## 좌석 범위

좌석 번호를 미리 고정하지 않고 실제 좌석맵의 행/열 위치를 기준으로 계산합니다.

| 설정 | 의미 |
|---|---|
| `prime` | 중앙 중간부 위주 |
| `good` | 중앙을 중심으로 앞뒤·좌우 확대 |
| `okay` | 기본값. 너무 앞/극단 사이드만 주로 제외 |
| `wide` | 최소한의 극단 좌석만 제외 |

용산 IMAX 좌석맵이 피드에 들어오면 각 행의 실제 좌석번호에 자동 적용됩니다.

## Discord Bot 준비

1. Discord Developer Portal에서 Application/Bot을 생성합니다.
2. Bot을 본인 서버에 초대합니다.
3. Bot Token을 복사합니다.
4. 알림을 받을 Discord 채널 ID를 확인합니다.
5. 저장소를 clone 한 뒤 `.env.example`을 `.env`로 복사합니다.

```bash
cp .env.example .env
```

`.env`:

```env
DISCORD_BOT_TOKEN=여기에_봇_토큰
DISCORD_GUILD_ID=본인_서버_ID
DISCORD_ALERT_CHANNEL_ID=알림_채널_ID
CGV_FEED_URL=http://localhost:8000/sample_feed.json
POLL_SECONDS=60
MAX_BACKOFF_SECONDS=900
```

**`.env`는 `.gitignore`에 포함되어 있습니다. 토큰을 GitHub에 커밋하지 마세요.**

## 설치/실행

Python 3.11+ 권장.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python run.py
```

### 샘플 데이터로 Discord UI 테스트

터미널 1:

```bash
python -m http.server 8000
```

`.env`에:

```env
CGV_FEED_URL=http://localhost:8000/sample_feed.json
```

터미널 2:

```bash
python run.py
```

Discord에서:

1. `/setup` → 기본 설정 저장
2. `/watch_menu` → `테스트 영화` → 날짜 선택
3. 샘플 피드의 좌석 상태를 바꾸면 신규 조건 충족 좌석에 대해서만 알림

## 좌석 피드 JSON 규격

```json
{
  "showings": [
    {
      "key": "unique-showing-id",
      "movie_id": "movie-id",
      "movie_name": "영화명",
      "date": "2026-08-23",
      "start_time": "19:40",
      "total_seats": 624,
      "remaining_seats": 2,
      "seats": [
        {"row": "H", "number": 22, "available": false},
        {"row": "H", "number": 23, "available": true},
        {"row": "H", "number": 24, "available": true}
      ]
    }
  ]
}
```

`key`는 같은 회차를 지속적으로 식별할 수 있는 고유값이어야 합니다.

## 안전 정책

- 최소 polling interval: 30초
- 기본: 60초
- HTTP 429: 지수 백오프
- HTTP 401/403: 자동 중지
- 자동 예매/좌석 선점/결제 없음
- CAPTCHA/Cloudflare/서명 우회 없음
- Discord Token 및 기타 비밀정보 저장소 커밋 금지

## 테스트

```bash
pip install pytest
pytest -q
```

현재 테스트는 좌석범위, 연석 판정, 설정 override 우선순위를 검증합니다.

## 다음 연결 단계

현재 남은 부분은 **CGV가 정상적으로 허용하는 방식으로 정확한 용산 IMAX 좌석맵을 공급하는 데이터 어댑터**입니다. 안전한 경로가 확인되면 `JsonFeed` 대신/앞단에 해당 adapter를 붙이면 Discord 흐름이나 좌석 판단 코드는 변경할 필요가 없습니다.

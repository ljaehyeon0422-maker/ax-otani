# TECHNICAL.md — 용산 IMAX 취소표 알리미 기술 문서

이 문서는 사용자용 README와 분리된 **개발·운영 전용 문서**다.

목적은 다음과 같다.

1. 현재 서비스가 어떻게 구동되는지 빠르게 파악한다.
2. Discord 사용자 경험과 내부 감시 로직을 분리해서 관리한다.
3. CGV 연결 방식이 바뀌더라도 좌석 판정/알림 로직은 최대한 건드리지 않는다.
4. 이후 ChatGPT/Codex가 저장소를 수정할 때 이 문서를 우선 참고해 일관성을 유지한다.

---

# 1. 최종 서비스 목표

사용자는 직접 프로그램을 실행하지 않는다.

```text
운영자
  └─ 봇 + 감시 서버를 24시간 실행
        ↓
Discord 서버
        ↓
사용자 초대 링크 입장
        ↓
/setup
        ↓
/watch_menu
        ↓
영화 / 날짜 선택
        ↓
개인별 조건 저장
        ↓
서버가 CGV 상태 감시
        ↓
조건 충족 취소표 발견
        ↓
Discord 알림
```

즉, 원본 `cgv-open-push`처럼 **운영자는 한 번 배포하고 사용자는 초대 링크만 받는 SaaS형 Discord Bot 구조**가 최종 목표다.

사용자에게 아래 작업을 요구하지 않는다.

- GitHub clone
- Python 설치
- `.env` 설정
- Discord Bot 직접 생성
- 개인 PC 24시간 실행

이 항목들은 모두 운영자 책임이다.

---

# 2. 현재 코드 구조

```text
ax-otani/
├─ README.md
├─ TECHNICAL.md
├─ .env.example
├─ requirements.txt
├─ run.py
├─ sample_feed.json
├─ src/
│  └─ imax_watcher/
│     ├─ bot.py
│     ├─ feed.py
│     ├─ models.py
│     ├─ seat_policy.py
│     ├─ store.py
│     └─ watcher.py
└─ tests/
   └─ test_seat_policy.py
```

핵심 책임은 다음과 같다.

## `bot.py`

Discord 사용자 인터페이스.

담당 기능:

- `/setup`
- `/watch_menu`
- `/watch`
- `/movie_override`
- `/watches`
- `/pause`
- `/resume`
- Discord Select Menu / Button
- 사용자별 설정 저장 호출
- watcher 백그라운드 태스크 시작

원칙:

> CGV 데이터 수집 로직을 `bot.py`에 직접 넣지 않는다.

---

## `feed.py`

외부 좌석 데이터를 내부 표준 모델로 변환하는 **Adapter Layer**다.

현재는 `JsonFeed`를 사용한다.

향후 CGV 데이터 접근 경로가 확정되면 이 레이어만 교체한다.

권장 구조:

```text
CGV / Browser / Allowed Feed
        ↓
   Feed Adapter
        ↓
List[Showing]
        ↓
Watcher / Seat Policy
```

즉, 나머지 코드에서는 CGV의 원본 JSON 필드명이나 HTML 구조를 알 필요가 없어야 한다.

---

## `models.py`

서비스 내부 표준 데이터 모델.

주요 개념:

- `Seat`
- `Showing`
- `Preferences`

CGV 연결부가 바뀌더라도 최종적으로 이 모델로 변환해야 한다.

---

## `seat_policy.py`

좌석 품질 및 연석 판정 엔진.

중요 원칙:

좌석 번호를 하드코딩하지 않는다.

예:

```text
H23~H26 = 명당
```

같은 방식은 좌석맵 변경이나 다른 상영관 확장 시 취약하다.

대신 실제 좌석맵에서의 상대적 위치를 계산한다.

```text
행 위치
+ 열 위치
+ 중앙에서의 거리
+ 앞/뒤 위치
```

이를 바탕으로 아래 네 등급을 적용한다.

```text
prime
  중앙 중간부 중심

good
  중앙부를 비교적 넓게 허용

okay
  기본값
  너무 앞쪽 / 극단 사이드만 제외

wide
  거의 전 좌석 허용
```

---

## `store.py`

SQLite 기반 사용자별 설정/감시 상태 저장.

설정 우선순위:

```text
User Profile
   ↓
Movie Override
   ↓
Watch Override
```

아래 설정이 위 설정을 덮어쓴다.

예:

```text
User default
2명 / okay / prefer_together

Movie A
3명 / good / all_together

Movie A + 2026-08-23
1명 / prime / any
```

8월 23일 Movie A는 마지막 설정으로 동작한다.

---

## `watcher.py`

실제 감시 루프.

주요 책임:

1. feed에서 최신 상영정보를 읽는다.
2. 활성화된 watch 목록을 불러온다.
3. 영화 + 날짜가 일치하는 회차를 찾는다.
4. 해당 watch의 최종 Preferences를 계산한다.
5. 조건을 만족하는 좌석 그룹을 찾는다.
6. 이전 상태와 비교한다.
7. 새로 등장한 조건 충족 좌석만 Discord 알림한다.

---

# 3. 사용자 UX 원칙

원본 `cgv-open-push`의 장점은 **사용자가 코드를 전혀 몰라도 Discord에 입장만 하면 된다**는 점이다.

이 프로젝트도 동일한 원칙을 따른다.

## 가입

```text
Discord 초대 링크 클릭
→ 서버 입장
```

## 최초 1회

```text
/setup
```

선택 항목:

```text
인원
좌석범위
연석조건
```

## 감시 등록

```text
/watch_menu
```

```text
영화 선택
→ 날짜 선택
→ 등록
```

가능한 한 사용자가 `movie_id`, `theater_code`, `screen_code` 등을 직접 입력하지 않게 한다.

---

# 4. Discord 서버 설계안

최종 운영 시 권장 채널:

```text
📢 안내
├─ #공지
├─ #사용방법
└─ #업데이트

🎬 알리미
├─ #명령어
└─ #취소표-알림

💬 지원
└─ GitHub Issues 링크 안내
```

현재는 단일 `DISCORD_ALERT_CHANNEL_ID`로 알림을 보낸다.

향후 확장 시 두 가지 방식이 가능하다.

## A. 공용 알림 채널

조건 충족 내용을 하나의 채널에 발송.

장점:

- 구현 단순
- 운영 쉬움

단점:

- 개인별 조건 노출 가능
- 사용자가 많아지면 알림 과다

## B. 개인 DM 알림 — 권장

`watch.user_id`를 기반으로 해당 사용자에게 DM 발송.

장점:

- 사용자별 설정과 정확히 매칭
- 알림 채널 혼잡 없음
- 개인 서비스 느낌이 강함

향후 우선 개선 후보다.

---

# 5. 데이터 수집 전략

가장 중요한 설계 원칙이다.

## 절대 피할 것

아래 기능을 서비스 핵심 로직에 넣지 않는다.

- CAPTCHA 우회
- Cloudflare 우회
- 차단 회피용 프록시 로테이션
- 숨겨진 비밀키/서명키 탈취
- 비정상적인 고빈도 호출
- 자동 좌석 선점
- 자동 결제

목표는 **취소표 탐지 알림**이지 예매 봇이 아니다.

---

# 6. 권장 데이터 수집 계층

향후 CGV 연결부는 다음 우선순위를 따른다.

## 1순위 — 공개/정상 접근 가능한 데이터

CGV가 사용자 브라우저에 정상 제공하는 일정/잔여좌석 정보 중 서버에서 허용되는 경로.

이를 이용할 수 있다면 가장 좋다.

---

## 2순위 — 정상 사용자 세션 내 브라우저 관찰

서버 직접 API 호출이 제한될 경우 고려할 수 있는 구조.

```text
정상 브라우저 세션
   ↓
페이지에서 사용자에게 이미 표시된 좌석 상태 읽기
   ↓
Local / Browser Adapter
   ↓
Watcher Feed
```

중요:

- 로그인 우회 금지
- CAPTCHA 자동 해결 금지
- 접근 제한 우회 금지

단순히 **정상적으로 렌더링된 데이터를 읽는 adapter**라는 원칙을 유지한다.

---

## 3순위 — 외부 허용 Feed

별도 서버/작업이 아래 포맷으로 데이터를 공급하도록 한다.

```json
{
  "showings": [
    {
      "key": "showing-key",
      "movie_id": "movie-id",
      "movie_name": "영화명",
      "date": "2026-08-23",
      "start_time": "19:40",
      "total_seats": 624,
      "remaining_seats": 2,
      "seats": [
        {
          "row": "H",
          "number": 23,
          "available": true
        }
      ]
    }
  ]
}
```

현재 `JsonFeed`가 이 방식이다.

---

# 7. API 호출 최소화 전략

원본 `cgv-open-push`는 과거 일정 응답의 변화를 주기적으로 비교하는 형태를 사용했다.

이 프로젝트는 취소표 좌석번호까지 필요하므로 더 보수적인 2단계 감시가 이상적이다.

```text
Stage 1
가벼운 상영정보 / 잔여좌석 수 확인

        ↓ 변화 있음

Stage 2
해당 회차 좌석맵 확인
```

예:

```text
19:40 IMAX
잔여좌석 0
→ 상세 좌석 조회 안 함

잔여좌석 0 → 2 변경
→ 해당 회차 좌석맵 확인
→ 조건에 맞는 H23,H24 확인
→ Discord 알림
```

이 방식이 구현 가능하면 좌석맵 전체 조회 빈도를 크게 줄일 수 있다.

---

# 8. Polling / Backoff 정책

현재 기본:

```text
POLL_SECONDS=60
최소 허용=30초
MAX_BACKOFF_SECONDS=900
```

권장 정책:

```text
정상
60초

일시 오류
120초

반복 오류
240초
480초
...

최대
900초
```

HTTP 상태 기준:

```text
429
→ 호출 빈도 자동 감소

401 / 403
→ 자동 우회하지 않음
→ watcher 중단 또는 긴 휴지
→ 운영자 알림
```

---

# 9. 중복 알림 방지 로직

핵심 상태 머신:

```text
AVAILABLE_NEW
   ↓
알림 발송
   ↓
AVAILABLE_ALREADY_NOTIFIED
   ↓
추가 알림 없음
   ↓
SOLD / UNAVAILABLE
   ↓
상태 제거
   ↓
다시 AVAILABLE
   ↓
새로운 취소표로 간주
   ↓
재알림
```

따라서 같은 좌석이 10분 동안 계속 비어 있다고 1분마다 알림하지 않는다.

---

# 10. 연석 판정

같은 행에서 좌석번호가 연속될 때 연석으로 본다.

예:

```text
H22 H23 H24
```

은 3연석.

```text
H22 H24
```

은 연석 아님.

통로 때문에 좌석번호가 연속되어도 물리적으로 떨어져 있는 특수 배치가 확인될 경우 향후 `seat_map adjacency graph` 방식으로 개선한다.

현재는 숫자 연속 방식이다.

---

# 11. 향후 우선 개발 순서

## Phase 1 — 현재

- Discord Bot 기본 UX
- 사용자 설정
- 영화별 override
- 날짜별 override
- 좌석 정책
- 연석 탐지
- 중복 알림 방지
- JSON Feed

## Phase 2 — 실제 CGV 데이터 연결

- 용산 IMAX 상영정보 adapter
- 좌석맵 adapter
- API 요청량 최소화
- 실제 좌석맵 기반 테스트

## Phase 3 — 운영형 Discord 서비스

- 24/7 호스팅
- 영구 DB volume
- Discord 초대 링크 발급
- DM 알림
- 관리자 명령어
- 장애 알림

## Phase 4 — 확장

- 용산 4DX
- SCREENX
- 다른 CGV IMAX
- 극장 선택 UI

---

# 12. 배포 권장 구조

개인 PC가 아니라 상시 실행되는 서버를 사용한다.

권장 예:

```text
Docker Container
├─ Discord Bot
├─ Watcher
└─ SQLite

Persistent Volume
└─ watcher.db
```

서비스 규모가 작으면 하나의 프로세스로 충분하다.

사용자가 늘어나면:

```text
Discord Bot
      ↓
PostgreSQL
      ↑
Watcher Worker
```

형태로 분리한다.

---

# 13. 초대 링크 구조

두 종류의 링크를 구분해야 한다.

## Discord Server Invite

사용자가 들어오는 링크.

예:

```text
https://discord.gg/xxxxx
```

최종 사용자에게 제공할 링크는 이것이다.

## Discord Bot OAuth Invite

봇을 새로운 서버에 설치하는 링크.

이 프로젝트의 기본 운영 방식에서는 일반 사용자에게 이 링크를 제공할 필요가 없다.

운영자가 하나의 공식 Discord 서버에 봇을 설치한 뒤 사용자는 **서버 초대 링크만 사용**한다.

---

# 14. 환경변수

현재:

```env
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
DISCORD_ALERT_CHANNEL_ID=
CGV_FEED_URL=
POLL_SECONDS=60
MAX_BACKOFF_SECONDS=900
```

향후 후보:

```env
ADMIN_USER_IDS=
DATABASE_URL=
LOG_CHANNEL_ID=
STATUS_CHANNEL_ID=
```

비밀값은 GitHub에 커밋하지 않는다.

---

# 15. 수정 시 지켜야 할 규칙

향후 코드 수정 시 아래 순서를 지킨다.

## CGV 데이터 구조 변경

`feed.py` 또는 별도 adapter만 우선 수정한다.

## 좌석 정책 변경

`seat_policy.py`만 수정한다.

## Discord UX 변경

`bot.py` 중심으로 수정한다.

## 사용자 데이터 구조 변경

`store.py` 수정 + migration 고려.

이 관심사 분리를 깨지 않는 것이 중요하다.

---

# 16. 다음 개발 작업

현재 가장 중요한 TODO는 아래 하나다.

> **용산 IMAX 실제 좌석 정보를 과도한 요청이나 접근 제한 우회 없이 안정적으로 Feed Adapter에 공급하는 방법 확정**

이 작업이 완료되면 나머지 구조는 그대로 사용할 수 있다.

그 다음 우선순위:

1. 공용 채널 대신 개인 DM 알림
2. 관리자 `/status` 명령어
3. watcher health check
4. Dockerfile
5. 클라우드 24/7 배포
6. Discord 서버 invite 링크 README 삽입

---

# 17. 참고 프로젝트

UX 및 운영 모델 참고:

`0w0i0n0g0/cgv-open-push`

참고할 핵심 아이디어:

```text
운영자가 서버에서 항상 실행
사용자는 Discord 초대만 받음
CGV 상태를 주기적으로 확인
변화 발생 시 Discord 알림
```

단, 이 저장소는 원본 소스에 종속되지 않도록 별도 구조로 유지한다.

원본 코드를 직접 가져오거나 수정하여 포함할 경우 반드시 원본 라이선스 조건을 검토한다.

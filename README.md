# LINE Gift Bot 🎁

LINE 채팅에서 축하 키워드를 감지하면 상황에 맞는 선물 추천 Flex Message를 자동으로 보내주는 챗봇.
Flex Message의 버튼을 누르면 LIFF 앱(생일 선물 랭킹 페이지)으로 이동한다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | Python + Flask |
| 프론트엔드 | HTML + CSS (vanilla) |
| LINE SDK | line-bot-sdk (Python, v3) |
| 외부 노출 | cloudflared (임시 터널) |

---

## 주요 기능

- **키워드 감지**: 한국어·중국어(번체/간체)·태국어·영어 축하 키워드 + 영어 줄임말(HBD 등) 자동 인식 (13개 카테고리)
- **카테고리별 Flex Message**: 상황(생일·결혼·이사·승진·출산·합격·졸업·취업·개업·기념일·새해·크리스마스·일반)에 맞는 카드 응답
- **4개 언어 자동 감지**: 입력 언어(한·영·중·태)에 따라 Flex Message + LIFF 페이지 UI 모두 자동 분기
- **멘션 친구 자동 선택**: @태그로 친구를 언급하면 LIFF 열릴 때 해당 친구가 자동 선택된 상태로 표시
- **LIFF 생일 선물 페이지**: Full 모드 LIFF — CSS 바텀시트 형태, 4개 언어 UI, 통화 기호 자동 적용
- **그룹 친구 선택**: 그룹 채팅에서 열면 친구 목록을 보여줌, 기본 프로필 이미지 4색 자동 배정
- **멤버 캐시**: 메시지를 보낸 멤버 프로필을 JSON 파일에 영구 저장

---

## Flex Message 디자인

모든 카테고리가 동일한 디자인 구조를 사용:

| 요소 | 스펙 |
|------|------|
| 버블 사이즈 | `kilo` |
| Hero 이미지 | `static/images/{category}_hero.png` / 비율 20:13 |
| 타이틀 | 16px Bold / 포인트 단어만 `#FF334B` / 나머지 `#111111` |
| 버튼 컬러 | `#FF334B` |
| 버튼 텍스트 | 14px Bold / White / Center |
| 버튼 높이 | 40px |
| 버튼 radius | 8px |
| 텍스트↔버튼 간격 | 14px |
| 버튼 구현 방식 | `box` + `text` 조합 (native button 미사용 — Bold 적용 위해) |

---

## 카테고리 목록

| 카테고리 | 감지 상황 | Hero 이미지 |
|----------|-----------|------------|
| `birthday` | 생일 | ✅ birthday_cake_hero.png |
| `wedding` | 결혼 | ❌ 미추가 |
| `moving` | 이사·집들이 | ❌ 미추가 |
| `promotion` | 승진 | ✅ promotion_hero.png |
| `baby` | 출산 | ❌ 미추가 |
| `exam` | 합격 | ✅ exam_hero_v2.png |
| `graduation` | 졸업 | ❌ 미추가 |
| `job` | 취업·취직 | ❌ 미추가 |
| `opening` | 개업·창업 | ❌ 미추가 |
| `anniversary` | 기념일 | ❌ 미추가 |
| `newyear` | 새해 | ❌ 미추가 |
| `christmas` | 크리스마스 | ❌ 미추가 |
| `general` | 일반 축하 (fallback) | ✅ general_hero.png |

카테고리별 키워드·타이틀·버튼 전체 목록은 `.claude/commands/categories.md` 참고.

---

## LIFF 생일 선물 페이지 (birthday_liff.html)

### 모드
- **Full 모드** (LINE Developers Console에서 설정)
- CSS로 바텀시트 외형 구현 (`height: 88vh`, `border-radius: 20px 20px 0 0`)
- `viewport-fit=cover` + `padding-bottom: env(safe-area-inset-bottom)` → iOS safe area 처리

### 뷰 구조
```
#sheet (88vh 바텀시트)
├── #sharedHeader (공유 헤더 — 뷰 전환 시 타이틀만 변경)
│   ├── "Birthday Gift" + X(liff.closeWindow)  ← 선물 뷰일 때
│   └── "Select Friend" + X(closeFriendSheet)  ← 친구 선택 뷰일 때
└── #viewContainer
    ├── .content (선물 뷰)
    │   ├── #profileSection (그룹 채팅 전용)
    │   │   ├── #profileDefault  — + 아이콘 + "Select a friend…"
    │   │   └── #profileSelected — 아바타 + "Birthday gift for\n{이름}" + Change 버튼
    │   └── #priceSections (가격대별 섹션 + 탭 + 캐러셀)
    └── .friend-sheet (친구 선택 뷰)
        ├── 검색바
        ├── 친구 목록 (아바타 + 이름 + 라디오 버튼)
        └── Select {이름} 버튼 (선택 시 표시)
```

### 친구 선택 동작
- 그룹 채팅에서만 `#profileSection` 표시
- 친구 선택 시 헤더 타이틀 → 친구 뷰로 전환, 선물 뷰 숨김
- 친구 확정 → 헤더 복원, 프로필 영역에 아바타+이름 표시
- 이름 10글자 초과 시 말줄임 처리
- 이름은 두 번째 줄에 표시: `{T.giftFor}\n{이름}`
- 프로필 없는 친구: 이름 해시 기반 기본 아바타 4색 자동 배정

### 멘션 자동 선택
- Flex Message에 `&mention={userId}` 파라미터 포함
- LIFF `<head>` 스크립트에서 즉시 `has-mention` CSS 클래스 적용 → 프로필 영역 완전 숨김
- 그룹 멤버 로드 완료 후 멘션 uid 매칭 → 자동 선택 → 프로필 영역 표시
- 깜빡임 없이 바로 선택된 상태로 표시

### 다국어
- Flex Message `lang` 파라미터 → LIFF URL로 전달
- `LANG_TEXT`: 헤더, 버튼, 통화 기호 등 ko/en/zh/th 분기
- `SECTIONS_I18N`: 섹션 제목 + 탭 이름 4개 언어
- 통화: 한국어=원, 영어/중국어=$, 태국어=฿, 3자리 쉼표 포맷

---

## 멤버 캐시 구조

`group_members_cache.json` (서버 루트):
```json
{
  "C{groupId}": {
    "U{userId}": { "name": "...", "img": "...", "userId": "..." }
  }
}
```

### 캐시 수집 방법
1. **메시지 이벤트**: 그룹에서 메시지 보낼 때마다 발신자 프로필 자동 저장
2. **MemberJoinedEvent**: 멤버 입장 시 자동 저장
3. **LIFF 자동 등록**: LIFF 열 때 현재 사용자 프로필 `/api/register-member`로 등록

### `/api/group-members` 동작
1. LINE API로 **전체 멤버 ID 목록** 항상 조회
2. 캐시에 있으면 캐시 사용, 없는 멤버만 LINE API로 프로필 추가 조회
3. LINE API 실패 시 캐시만 반환

---

## 설치 방법

### 1. 의존성 설치

```bash
pip3 install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일에 아래 값을 입력:

```
LINE_CHANNEL_ACCESS_TOKEN=발급받은_토큰
LINE_CHANNEL_SECRET=채널_시크릿
LIFF_ID=LIFF_앱_ID
SERVER_URL=https://xxxx.trycloudflare.com
```

| 변수 | 설명 | 확인 위치 |
|------|------|-----------|
| `LINE_CHANNEL_ACCESS_TOKEN` | Messaging API 인증 토큰 | LINE Developers Console → Messaging API |
| `LINE_CHANNEL_SECRET` | Webhook 서명 검증용 시크릿 | LINE Developers Console → Messaging API |
| `LIFF_ID` | LIFF 앱 식별자 | LINE Developers Console → LIFF |
| `SERVER_URL` | Hero 이미지 공개 URL 베이스 | cloudflared 실행 후 터미널 로그에서 확인 |

> `.env` 값 변경 후 반드시 서버 재시작 필요 (Flask는 시작 시 한 번만 읽음)

### 3. LIFF 설정

LINE Developers Console → LIFF → Size: **Full** (반드시 Full 모드)

### 4. cloudflared 설치 (미설치 시)

```bash
brew install cloudflared
```

---

## 실행 방법

```bash
./start.sh
```

실행 후 터미널 로그에서 URL 확인:

```
https://xxxx.trycloudflare.com
```

LINE Developers Console에서 세 곳을 업데이트:

| 항목 | 값 |
|------|----|
| Webhook URL | `https://xxxx.trycloudflare.com/webhook` |
| LIFF Endpoint URL | `https://xxxx.trycloudflare.com/liff` |
| `.env` SERVER_URL | `https://xxxx.trycloudflare.com` |

> **주의**: cloudflared 임시 터널은 재시작할 때마다 URL이 바뀌므로, 매번 위 세 곳을 함께 업데이트해야 한다.

---

## 파일 구조

```
Gift bot/
├── app.py                          # Flask 서버 (Webhook·Flex Message·LIFF·멤버 API)
├── requirements.txt                # Python 의존성
├── start.sh                        # Flask + cloudflared 한 번에 실행
├── app.log                         # Flask 실행 로그
├── group_members_cache.json        # 그룹 멤버 프로필 캐시 (자동 생성)
├── .env                            # 환경변수 — 시크릿 (Git 제외)
├── .gitignore
├── static/
│   └── images/
│       ├── birthday_cake_hero.png  # 생일 Hero 이미지
│       ├── promotion_hero.png      # 승진 Hero 이미지
│       ├── exam_hero_v2.png        # 합격 Hero 이미지
│       ├── general_hero.png        # 일반 축하 Hero 이미지
│       ├── profile_default_0.svg   # 기본 프로필 (파랑 #D5E3FD)
│       ├── profile_default_1.svg   # 기본 프로필 (하늘 #C8E9F9)
│       ├── profile_default_2.svg   # 기본 프로필 (보라 #DFE0FB)
│       └── profile_default_3.svg   # 기본 프로필 (초록 #C6ECE1)
└── templates/
    ├── index.html                  # /liff 접근 시 /liff/birthday로 즉시 리다이렉트
    └── birthday_liff.html          # 생일 선물 LIFF 페이지 (Full 모드, 친구 선택, 다국어)
```

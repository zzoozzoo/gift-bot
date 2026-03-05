# gift-bot

LINE 채팅방에서 축하 키워드를 감지하면 선물 추천 Flex Message를 자동으로 응답하는 LINE OA 봇.
버튼을 누르면 LIFF 앱(생일 선물 랭킹 페이지)으로 이동해 가격대별 인기 상품을 확인할 수 있다.

---

## 주요 기능

- **키워드 감지**: 한국어·중국어·태국어·영어 / 13개 카테고리 (생일·결혼·승진·합격 등)
- **카테고리별 Flex Message**: 카테고리·언어 자동 감지 → 맞춤 디자인 메시지
- **LIFF 선물 랭킹**: 가격대별($600 이하) 인기 상품 / 케이크·커피·뷰티 카테고리
- **상품 자동 수집**: LINE Gift Shop API + Google Trends → 매주 Top 16 자동 갱신
- **친구 선택**: 그룹 내 멤버 조회 → 선물 받을 친구 지정
- **멘션 자동 선택**: @태그 시 해당 친구 프로필 즉시 표시

---

## 프로젝트 구조

```
Gift bot/
├── app.py                        # Flask 서버 (Webhook·Flex Message·LIFF·멤버 API)
├── requirements.txt              # Python 의존성
├── start.sh                      # Flask + cloudflared 동시 실행 스크립트
├── .env                          # 환경변수 (Git 제외)
├── scripts/
│   └── fetch_top16.py            # 상품 수집 스크립트
├── .github/workflows/
│   └── update_products.yml       # 매주 월요일 자동 실행 (GitHub Actions)
├── static/
│   ├── images/                   # Hero 이미지, 기본 프로필 SVG
│   └── data/
│       ├── top16_cake.json       # 케이크·디저트 Top 16
│       ├── top16_coffee.json     # 커피·음료 Top 16
│       └── top16_beauty.json     # 뷰티·케어 Top 16
└── templates/
    ├── index.html                # /liff 리다이렉트
    └── birthday_liff.html        # 생일 선물 LIFF 페이지
```

---

## 로컬 실행

### 1. 의존성 설치

```bash
pip3 install -r requirements.txt
pip3 install pytrends  # 상품 수집 스크립트용
```

### 2. 환경변수 설정

`.env` 파일 생성:

```
LINE_CHANNEL_ACCESS_TOKEN=발급받은_토큰
LINE_CHANNEL_SECRET=채널_시크릿
LIFF_ID=LIFF_앱_ID
SERVER_URL=https://xxxx.trycloudflare.com
```

### 3. 서버 시작

```bash
./start.sh
```

실행 후 cloudflared 로그에서 URL 확인 → LINE Developers Console에서 아래 세 곳 업데이트:
1. Webhook URL: `https://xxxx.trycloudflare.com/webhook`
2. LIFF Endpoint URL: `https://xxxx.trycloudflare.com/liff`
3. `.env` → `SERVER_URL=https://xxxx.trycloudflare.com`

---

## 상품 데이터 파이프라인

### 수동 실행

```bash
python3 scripts/fetch_top16.py
```

케이크·커피·뷰티 3개 카테고리를 순서대로 처리하고 `static/data/top16_*.json`을 저장한다.

### 자동 실행 (GitHub Actions)

매주 월요일 09:00 KST에 자동으로 실행되며, 결과 JSON을 저장소에 커밋한다.

수동 실행은 GitHub → Actions 탭 → "Update Top 16 Products" → "Run workflow".

### 채점 방식

```
최종 점수 = LINE 인기도 40% + Google Trends 키워드 매칭 60%
```

- **LINE 인기도**: `recentSaleCount` min-max 정규화
- **Trends**: 카테고리 키워드로 `related_queries()` 조회, 급상승(rising) 2배 가중치
- 브랜드별 최대 3개 / 항상 16개 채움

### GitHub Secrets (Actions 실행 시 선택 설정)

| Secret | 설명 |
|--------|------|
| `LINE_COOKIE` | 브라우저 DevTools Network 탭에서 복사 |
| `LINE_CSRF_TOKEN` | `x-csrf-token` 요청 헤더값 |

---

## LINE Developers Console 설정

| 항목 | 값 |
|------|----|
| Messaging API | Webhook URL 등록 필요 |
| LIFF | Size: **Full** / Endpoint URL 등록 필요 |
| Permissions | `profile`, `openid` |

---

## 환경 요구사항

- Python 3.11+
- cloudflared (`brew install cloudflared`)
- LINE Business Account + Messaging API 채널
- LIFF 앱 생성

import os
from flask import Flask, request, abort, render_template, make_response, jsonify, redirect
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, GroupSource, RoomSource, MemberJoinedEvent
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    FlexMessage,
)
from linebot.v3.messaging.models import FlexContainer
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

app = Flask(__name__)

# ── 멤버 캐시 파일 저장/로드 ───────────────────────────────────────────────────
import json

CACHE_FILE = os.path.join(os.path.dirname(__file__), "group_members_cache.json")

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CACHE] save error: {e}")

# 그룹/룸별 멤버 프로필 캐시: { group_or_room_id: { user_id: {name, img, userId} } }
group_members_cache: dict = load_cache()
print(f"[CACHE] loaded {sum(len(v) for v in group_members_cache.values())} members from file")

configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
LIFF_ID = os.getenv("LIFF_ID")
SERVER_URL = os.getenv("SERVER_URL", "")

# ── 카테고리별 키워드 ─────────────────────────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "birthday": [
        # 한국어
        "생일축하", "생일 축하", "생축", "생일추카", "생일 추카",
        # 중국어
        "生日快樂",
        # 태국어
        "สุขสันต์วันเกิด",
        # 영어
        "happy birthday", "hbd",
    ],
    "wedding": [
        # 한국어
        "결혼 축하", "결혼축하", "결혼 축하해", "결혼 축하해요", "결혼 축하합니다", "결혼 축하드려요",
        "결혼 추카", "결혼추카", "결혼 추카해", "결혼 추카해요", "결혼 추카합니다",
        # 중국어 (번체)
        "結婚快樂", "恭喜結婚", "恭賀新婚", "新婚快樂", "百年好合", "新婚之喜",
        # 중국어 (간체)
        "结婚快乐", "恭喜结婚", "新婚愉快", "恭贺新婚",
        # 태국어
        "ยินดีกับการแต่งงาน", "ขอแสดงความยินดีกับการแต่งงาน", "ยินดีกับการสมรส",
        # 영어
        "happy wedding", "congratulations on your wedding", "congratulations on getting married", "congrats on your marriage", "congrats on the wedding", "congrats on getting married",
    ],
    "moving": [
        # 한국어
        "이사 축하", "이사축하", "이사 축하해", "이사 축하해요", "이사 축하합니다",
        "집들이 축하", "집들이 축하해", "집들이 축하합니다", "새집 축하",
        "이사 추카", "이사추카", "이사 추카해", "집들이 추카", "새집 추카",
        # 중국어 (번체)
        "恭賀喬遷", "喬遷之喜", "喬遷快樂", "恭喜喬遷", "新居快樂", "入厝快樂",
        # 중국어 (간체)
        "乔迁之喜", "乔迁快乐", "恭喜乔迁",
        # 태국어
        "ยินดีกับบ้านใหม่", "ยินดีกับการย้ายบ้าน", "ขอแสดงความยินดีกับบ้านใหม่",
        # 영어
        "happy housewarming", "congratulations on your new home", "congrats on the new house", "congrats on the new home",
    ],
    "promotion": [
        # 한국어
        "승진 축하", "승진축하", "승진 추카", "승진추카",
        # 중국어
        "升職快樂", "恭喜升職", "荣升之喜",
        # 태국어
        "ยินดีกับการเลื่อนตำแหน่ง",
        # 영어
        "congratulations on your promotion", "congrats on the promotion", "congrats on the promo",
    ],
    "baby": [
        # 한국어
        "출산 축하", "출산축하", "출산 축하해", "출산 축하해요", "출산 축하합니다", "아기 탄생 축하",
        "출산 추카", "출산추카", "아기 탄생 추카",
        # 중국어
        "恭喜得子", "恭喜生產", "恭喜添丁", "母子平安", "弄璋之喜", "弄瓦之喜", "恭喜生子",
        # 태국어
        "ยินดีกับลูกน้อย", "ยินดีกับการมีลูก", "ขอแสดงความยินดีกับการคลอด", "ยินดีกับเจ้าตัวน้อย",
        # 영어
        "congratulations on your baby", "congratulations on your new baby", "congrats on the baby", "welcome baby", "congrats on the newborn",
    ],
    "exam": [
        # 한국어
        "합격 축하", "합격축하", "합격 축하해", "합격 축하해요", "합격 축하합니다",
        "합격 추카", "합격추카", "합격 추카해",
        # 중국어
        "恭喜錄取", "金榜題名", "恭喜考上", "考試合格", "恭喜及格", "恭喜通過",
        "金榜题名", "恭喜录取",
        # 태국어
        "ยินดีกับการสอบผ่าน", "ยินดีกับการสอบติด", "ขอแสดงความยินดีกับการสอบ",
        # 영어
        "congratulations on passing", "congratulations on your acceptance", "congrats on passing", "congrats on the exam", "passed the exam",
    ],
    "graduation": [
        # 한국어
        "졸업 축하", "졸업축하", "졸업 축하해", "졸업 축하해요", "졸업 축하합니다",
        "졸업 추카", "졸업추카", "졸업 추카해",
        # 중국어
        "恭喜畢業", "畢業快樂", "恭喜毕业", "毕业快乐",
        # 태국어
        "ยินดีกับการจบการศึกษา", "ยินดีกับการสำเร็จการศึกษา", "ขอแสดงความยินดีกับการจบการศึกษา",
        # 영어
        "happy graduation", "congratulations on your graduation", "congrats on graduating", "happy grad", "congrats on grad",
    ],
    "job": [
        # 한국어
        "취업 축하", "취업축하", "취업 축하해", "취업 축하해요", "취업 축하합니다",
        "취직 축하", "취직축하", "취직 축하해", "취직 축하합니다",
        "취업 추카", "취업추카", "취직 추카", "취직추카",
        # 중국어
        "恭喜就業", "恭喜入職", "就職之喜", "恭喜就业", "恭喜入职",
        # 태국어
        "ยินดีกับการได้งาน", "ยินดีกับงานใหม่", "ขอแสดงความยินดีกับการทำงาน", "ยินดีกับการเริ่มงาน",
        # 영어
        "congratulations on your new job", "congratulations on getting the job", "congrats on the job", "congrats on the new job", "new job congrats",
    ],
    "opening": [
        # 한국어
        "개업 축하", "개업축하", "개업 축하해", "개업 축하해요", "개업 축하합니다",
        "창업 축하", "창업축하", "창업 축하해", "창업 축하합니다", "오픈 축하",
        "개업 추카", "개업추카", "창업 추카", "창업추카", "오픈 추카",
        # 중국어
        "恭喜開業", "開業大吉", "恭賀開業", "生意興隆", "開張大吉", "恭喜開張",
        "恭喜开业", "开业大吉", "开张大吉",
        # 태국어
        "ยินดีกับการเปิดร้าน", "ยินดีกับการเปิดกิจการ", "ขอแสดงความยินดีกับการเปิดร้าน", "ยินดีกับธุรกิจใหม่",
        # 영어
        "congratulations on your grand opening", "congratulations on your new business", "happy grand opening", "congrats on opening", "congrats on the opening", "grand opening",
    ],
    "anniversary": [
        # 한국어
        "기념일 축하", "기념일축하", "기념일 축하해", "기념일 축하해요", "기념일 축하합니다",
        "결혼기념일 축하", "결혼 기념일 축하",
        "기념일 추카", "기념일추카", "결혼기념일 추카", "결혼 기념일 추카",
        # 중국어
        "周年紀念", "紀念日快樂", "結婚紀念日快樂", "周年快乐", "纪念日快乐",
        # 태국어
        "ยินดีกับวันครบรอบ", "ขอแสดงความยินดีกับวันครบรอบ", "ยินดีกับวันครบรอบแต่งงาน",
        # 영어
        "happy anniversary", "congratulations on your anniversary", "congrats on your anniversary", "happy anni", "happy anniv",
    ],
    "newyear": [
        # 한국어
        "새해 복 많이", "새해복", "새해 복", "새해복많이", "새해 인사",
        # 중국어 (번체)
        "新年快樂", "恭喜發財", "恭賀新年", "新春快樂", "恭賀新禧",
        # 중국어 (간체)
        "新年好", "恭喜发财", "新春快乐",
        # 태국어
        "สวัสดีปีใหม่", "สุขสันต์ปีใหม่",
        # 영어
        "happy new year", "hny",
    ],
    "christmas": [
        # 한국어
        "메리 크리스마스", "메리크리스마스", "크리스마스 축하", "성탄절 축하", "즐거운 크리스마스",
        "크리스마스 추카", "성탄절 추카",
        # 중국어 (번체)
        "聖誕快樂", "聖誕節快樂", "恭賀聖誕",
        # 중국어 (간체)
        "圣诞快乐", "圣诞节快乐",
        # 태국어
        "สุขสันต์วันคริสต์มาส", "เมอร์รี่คริสต์มาส",
        # 영어
        "merry christmas", "happy christmas", "season's greetings", "merry xmas", "happy xmas",
    ],
    "general": [
        # 한국어
        "축하", "추카",
        # 중국어 (번체)
        "恭喜", "祝賀", "恭賀",
        # 태국어
        "ยินดีด้วย", "ขอแสดงความยินดี",
        # 영어
        "congratulations", "congrats", "gz", "gratz", "grats",
    ],
}

# 역방향 매핑: keyword.lower() → category (빠른 카테고리 조회용)
KEYWORD_CATEGORY: dict[str, str] = {
    kw.lower(): cat
    for cat, keywords in CATEGORY_KEYWORDS.items()
    for kw in keywords
}

# 플랫 리스트 (detect_keyword 순서 유지용)
KEYWORDS: list[str] = [kw for keywords in CATEGORY_KEYWORDS.values() for kw in keywords]


# ── 생일 키워드 → 언어 매핑 ──────────────────────────────────────────────────
BIRTHDAY_KEYWORD_LANG: dict[str, str] = {
    "생일축하": "ko",
    "생일 축하": "ko",
    "생축": "ko",
    "생일추카": "ko",
    "생일 추카": "ko",
    "生日快樂": "zh",
    "สุขสันต์วันเกิด": "th",
    "happy birthday": "en",
    "hbd": "en",
}

BIRTHDAY_I18N: dict[str, dict[str, str]] = {
    "ko": {
        "title_before": "친구의 ",
        "title_highlight": "생일",
        "title_after": "을\n특별하게 만들어보세요!",
        "button": "축하 선물하기",
        "alt_text": "친구의 생일을 특별하게 만들어보세요!",
    },
    "en": {
        "title_before": "Make your friend's ",
        "title_highlight": "birthday",
        "title_after": "\nextra special!",
        "button": "Send a Gift",
        "alt_text": "Make your friend's birthday extra special!",
    },
    "zh": {
        "title_before": "讓朋友的",
        "title_highlight": "生日",
        "title_after": "更加特別！",
        "button": "送禮祝賀",
        "alt_text": "讓朋友的生日更加特別！",
    },
    "th": {
        "title_before": "ทำให้",
        "title_highlight": "วันเกิด",
        "title_after": "\nของเพื่อนพิเศษยิ่งขึ้น!",
        "button": "ส่งของขวัญ",
        "alt_text": "ทำให้วันเกิดของเพื่อนพิเศษยิ่งขึ้น!",
    },
}


# ── 카테고리별 설정 (다국어: ko / en / zh / th) ──────────────────────────────
CATEGORY_CONFIG: dict[str, dict[str, dict]] = {
    "moving": {
        "ko": {"title_before": "친구의 ",         "title_highlight": "새 보금자리", "title_after": "를\n따뜻하게 만들어주세요!",       "button": "축하 선물하기",     "alt_text": "친구의 새 보금자리를 따뜻하게 만들어주세요!"},
        "en": {"title_before": "Warm up your friend's ", "title_highlight": "new home",  "title_after": "\nwith a special gift!",        "button": "Send a Gift",       "alt_text": "Warm up your friend's new home with a special gift!"},
        "zh": {"title_before": "讓朋友的",         "title_highlight": "新居",       "title_after": "充滿溫暖！",                     "button": "送禮祝賀",       "alt_text": "讓朋友的新居充滿溫暖！"},
        "th": {"title_before": "ทำให้",            "title_highlight": "บ้านใหม่",  "title_after": "\nของเพื่อนอบอุ่นยิ่งขึ้น!",     "button": "ส่งของขวัญ",        "alt_text": "ทำให้บ้านใหม่ของเพื่อนอบอุ่นยิ่งขึ้น!"},
    },
    "promotion": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "승진",        "title_after": "을\n더 빛나게 해주세요!",          "button": "축하 선물하기",     "alt_text": "친구의 승진을 더 빛나게 해주세요!"},
        "en": {"title_before": "Make your friend's ", "title_highlight": "promotion", "title_after": "\neven more brilliant!",          "button": "Send a Gift",       "alt_text": "Make your friend's promotion even more brilliant!"},
        "zh": {"title_before": "讓朋友的",          "title_highlight": "升職",        "title_after": "更加耀眼！",                     "button": "送禮祝賀",       "alt_text": "讓朋友的升職更加耀眼！"},
        "th": {"title_before": "ทำให้",             "title_highlight": "การเลื่อนตำแหน่ง", "title_after": "\nของเพื่อนยิ่งสดใส!",   "button": "ส่งของขวัญ",        "alt_text": "ทำให้การเลื่อนตำแหน่งของเพื่อนยิ่งสดใส!"},
    },
    "graduation": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "졸업",        "title_after": "을\n오래 기억에 남게 해보세요!",    "button": "축하 선물하기",     "alt_text": "친구의 졸업을 오래 기억에 남게 해보세요!"},
        "en": {"title_before": "Make your friend's ", "title_highlight": "graduation","title_after": "\nunforgettable!",               "button": "Send a Gift",       "alt_text": "Make your friend's graduation unforgettable!"},
        "zh": {"title_before": "讓朋友的",          "title_highlight": "畢業",        "title_after": "成為美好的回憶！",               "button": "送禮祝賀",       "alt_text": "讓朋友的畢業成為美好的回憶！"},
        "th": {"title_before": "ทำให้",             "title_highlight": "การจบการศึกษา", "title_after": "\nของเพื่อนน่าจดจำ!",        "button": "ส่งของขวัญ",        "alt_text": "ทำให้การจบการศึกษาของเพื่อนน่าจดจำ!"},
    },
    "wedding": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "결혼",        "title_after": "을\n더 특별하게 만들어보세요!",     "button": "축하 선물하기",     "alt_text": "친구의 결혼을 더 특별하게 만들어보세요!"},
        "en": {"title_before": "Make your friend's ", "title_highlight": "wedding",   "title_after": "\nextra special!",               "button": "Send a Gift",       "alt_text": "Make your friend's wedding extra special!"},
        "zh": {"title_before": "讓朋友的",          "title_highlight": "婚禮",        "title_after": "更加特別！",                     "button": "送禮祝賀",       "alt_text": "讓朋友的婚禮更加特別！"},
        "th": {"title_before": "ทำให้",             "title_highlight": "งานแต่งงาน","title_after": "\nของเพื่อนพิเศษยิ่งขึ้น!",     "button": "ส่งของขวัญ",        "alt_text": "ทำให้งานแต่งงานของเพื่อนพิเศษยิ่งขึ้น!"},
    },
    "baby": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "새 가족",     "title_after": "을\n따뜻하게 맞이해보세요!",        "button": "축하 선물하기",     "alt_text": "친구의 새 가족을 따뜻하게 맞이해보세요!"},
        "en": {"title_before": "Welcome your friend's ", "title_highlight": "new baby","title_after": "\nwith a warm gift!",           "button": "Send a Gift",       "alt_text": "Welcome your friend's new baby with a warm gift!"},
        "zh": {"title_before": "用溫暖的禮物迎接",  "title_highlight": "新生命",      "title_after": "的到來！",                       "button": "送禮祝賀",       "alt_text": "用溫暖的禮物迎接新生命的到來！"},
        "th": {"title_before": "ต้อนรับ",           "title_highlight": "สมาชิกใหม่", "title_after": "\nของเพื่อนอย่างอบอุ่น!",        "button": "ส่งของขวัญ",        "alt_text": "ต้อนรับสมาชิกใหม่ของเพื่อนอย่างอบอุ่น!"},
    },
    "exam": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "합격",        "title_after": "을\n더 빛나게 해주세요!",          "button": "축하 선물하기",     "alt_text": "친구의 합격을 더 빛나게 해주세요!"},
        "en": {"title_before": "Celebrate your friend's ", "title_highlight": "success","title_after": "\nwith a special gift!",       "button": "Send a Gift",       "alt_text": "Celebrate your friend's success with a special gift!"},
        "zh": {"title_before": "讓朋友的",          "title_highlight": "錄取",        "title_after": "更加閃耀！",                     "button": "送禮祝賀",       "alt_text": "讓朋友的錄取更加閃耀！"},
        "th": {"title_before": "ฉลอง",             "title_highlight": "ความสำเร็จ", "title_after": "\nของเพื่อนด้วยของขวัญ!",         "button": "ส่งของขวัญ",        "alt_text": "ฉลองความสำเร็จของเพื่อนด้วยของขวัญ!"},
    },
    "job": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "새 출발",     "title_after": "을\n응원해보세요!",                "button": "축하 선물하기",     "alt_text": "친구의 새 출발을 응원해보세요!"},
        "en": {"title_before": "Cheer on your friend's ", "title_highlight": "new journey","title_after": "\nwith a special gift!",    "button": "Send a Gift",       "alt_text": "Cheer on your friend's new journey with a special gift!"},
        "zh": {"title_before": "為朋友的",          "title_highlight": "新出發",      "title_after": "加油打氣！",                     "button": "送禮祝賀",       "alt_text": "為朋友的新出發加油打氣！"},
        "th": {"title_before": "เป็นกำลังใจให้",   "title_highlight": "การเริ่มต้นใหม่","title_after": "\nของเพื่อน!",              "button": "ส่งของขวัญ",        "alt_text": "เป็นกำลังใจให้การเริ่มต้นใหม่ของเพื่อน!"},
    },
    "opening": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "새 시작",     "title_after": "을\n함께 응원해보세요!",            "button": "축하 선물하기",     "alt_text": "친구의 새 시작을 함께 응원해보세요!"},
        "en": {"title_before": "Cheer on your friend's ", "title_highlight": "grand opening","title_after": "\ntogether!",            "button": "Send a Gift",       "alt_text": "Cheer on your friend's grand opening together!"},
        "zh": {"title_before": "為朋友的",          "title_highlight": "開業",        "title_after": "送上最誠摯的祝福！",             "button": "送禮祝賀",       "alt_text": "為朋友的開業送上最誠摯的祝福！"},
        "th": {"title_before": "เป็นกำลังใจให้",   "title_highlight": "การเปิดกิจการ","title_after": "\nของเพื่อนด้วยกัน!",          "button": "ส่งของขวัญ",        "alt_text": "เป็นกำลังใจให้การเปิดกิจการของเพื่อนด้วยกัน!"},
    },
    "anniversary": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "기념일",      "title_after": "을\n더 특별하게 만들어보세요!",     "button": "축하 선물하기",     "alt_text": "친구의 기념일을 더 특별하게 만들어보세요!"},
        "en": {"title_before": "Make your friend's ", "title_highlight": "anniversary","title_after": "\nextra special!",              "button": "Send a Gift",       "alt_text": "Make your friend's anniversary extra special!"},
        "zh": {"title_before": "讓朋友的",          "title_highlight": "紀念日",      "title_after": "更加難忘！",                     "button": "送禮祝賀",       "alt_text": "讓朋友的紀念日更加難忘！"},
        "th": {"title_before": "ทำให้",             "title_highlight": "วันครบรอบ",  "title_after": "\nของเพื่อนพิเศษยิ่งขึ้น!",     "button": "ส่งของขวัญ",        "alt_text": "ทำให้วันครบรอบของเพื่อนพิเศษยิ่งขึ้น!"},
    },
    "newyear": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "새해",        "title_after": "를\n더 특별하게 만들어보세요!",     "button": "새해 선물하기",     "alt_text": "친구의 새해를 더 특별하게 만들어보세요!"},
        "en": {"title_before": "Make your friend's ", "title_highlight": "New Year",  "title_after": "\nextra special!",               "button": "Send a Gift",       "alt_text": "Make your friend's New Year extra special!"},
        "zh": {"title_before": "讓朋友的",          "title_highlight": "新年",        "title_after": "更加特別！",                     "button": "送禮祝賀",       "alt_text": "讓朋友的新年更加特別！"},
        "th": {"title_before": "ทำให้",             "title_highlight": "ปีใหม่",     "title_after": "\nของเพื่อนพิเศษยิ่งขึ้น!",     "button": "ส่งของขวัญ",        "alt_text": "ทำให้ปีใหม่ของเพื่อนพิเศษยิ่งขึ้น!"},
    },
    "christmas": {
        "ko": {"title_before": "친구의 ",          "title_highlight": "크리스마스",  "title_after": "를\n더 특별하게 만들어보세요!",     "button": "크리스마스 선물하기", "alt_text": "친구의 크리스마스를 더 특별하게 만들어보세요!"},
        "en": {"title_before": "Make your friend's ", "title_highlight": "Christmas", "title_after": "\nextra special!",               "button": "Send a Gift",       "alt_text": "Make your friend's Christmas extra special!"},
        "zh": {"title_before": "讓朋友的",          "title_highlight": "聖誕節",      "title_after": "更加特別！",                     "button": "送禮祝賀",       "alt_text": "讓朋友的聖誕節更加特別！"},
        "th": {"title_before": "ทำให้",             "title_highlight": "คริสต์มาส", "title_after": "\nของเพื่อนพิเศษยิ่งขึ้น!",     "button": "ส่งของขวัญ",        "alt_text": "ทำให้คริสต์มาสของเพื่อนพิเศษยิ่งขึ้น!"},
    },
    "general": {
        "ko": {"title_before": "친구를 더 특별하게\n축하해주세요!",                    "title_highlight": "", "title_after": "", "button": "축하 선물하기",     "alt_text": "친구를 더 특별하게 축하해주세요!"},
        "en": {"title_before": "Make it extra special\nfor your friend!",             "title_highlight": "", "title_after": "", "button": "Send a Gift",       "alt_text": "Make it extra special for your friend!"},
        "zh": {"title_before": "讓朋友的祝賀更加特別！",                               "title_highlight": "", "title_after": "", "button": "送禮祝賀",           "alt_text": "讓朋友的祝賀更加特別！"},
        "th": {"title_before": "ทำให้การฉลอง\nของเพื่อนพิเศษยิ่งขึ้น!",            "title_highlight": "", "title_after": "", "button": "ส่งของขวัญ",        "alt_text": "ทำให้การฉลองของเพื่อนพิเศษยิ่งขึ้น!"},
    },
}


def detect_keyword_lang(keyword: str) -> str:
    """키워드 문자셋으로 언어 감지 (ko / zh / th / en)."""
    for ch in keyword:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
            return "ko"
        if 0x0E00 <= code <= 0x0E7F:
            return "th"
        if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            return "zh"
    return "en"


def detect_keyword(text: str) -> Optional[str]:
    """텍스트에서 첫 번째 매칭 키워드를 반환."""
    lower = text.lower()
    for kw in KEYWORDS:
        if kw.lower() in lower:
            return kw
    return None


def build_birthday_flex_message(lang: str, group_id: str = "", mention_uid: str = "") -> FlexMessage:
    """피그마 디자인 기반 생일 전용 Flex Message."""
    gid_param = f"&gid={group_id}" if group_id else ""
    mention_param = f"&mention={mention_uid}" if mention_uid else ""
    liff_url = f"https://liff.line.me/{LIFF_ID}/birthday?lang={lang}{gid_param}{mention_param}"
    image_url = f"{SERVER_URL}/static/images/birthday_cake_hero.png"
    i18n = BIRTHDAY_I18N[lang]

    flex_dict = {
        "type": "bubble",
        "size": "kilo",
        "hero": {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {
                "type": "uri",
                "uri": liff_url
            }
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingTop": "16px",
            "paddingStart": "16px",
            "paddingEnd": "16px",
            "paddingBottom": "0px",
            "backgroundColor": "#ffffff",
            "contents": [
                {
                    "type": "text",
                    "size": "16px",
                    "weight": "bold",
                    "wrap": True,
                    "contents": [
                        {
                            "type": "span",
                            "text": i18n["title_before"],
                            "color": "#111111"
                        },
                        {
                            "type": "span",
                            "text": i18n["title_highlight"],
                            "color": "#ff334b"
                        },
                        {
                            "type": "span",
                            "text": i18n["title_after"],
                            "color": "#111111"
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingTop": "14px",
            "paddingStart": "12px",
            "paddingEnd": "12px",
            "paddingBottom": "12px",
            "backgroundColor": "#ffffff",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "height": "40px",
                    "cornerRadius": "8px",
                    "backgroundColor": "#ff334b",
                    "justifyContent": "center",
                    "action": {
                        "type": "uri",
                        "uri": liff_url
                    },
                    "contents": [
                        {
                            "type": "text",
                            "text": i18n["button"],
                            "color": "#ffffff",
                            "weight": "bold",
                            "size": "14px",
                            "align": "center"
                        }
                    ]
                }
            ]
        }
    }

    return FlexMessage(
        alt_text=i18n["alt_text"],
        contents=FlexContainer.from_dict(flex_dict)
    )


def build_category_flex_message(category: str, lang: str) -> FlexMessage:
    """카테고리별 전용 Flex Message (생일과 동일한 디자인)."""
    liff_url = f"https://liff.line.me/{LIFF_ID}"
    category_hero_map = {
        "exam": "exam_hero_v2.png",
    }
    hero_filename = category_hero_map.get(category, f"{category}_hero.png")
    image_url = f"{SERVER_URL}/static/images/{hero_filename}"
    cfg = CATEGORY_CONFIG[category].get(lang, CATEGORY_CONFIG[category]["ko"])

    if cfg["title_highlight"]:
        title_contents = [
            {"type": "span", "text": cfg["title_before"], "color": "#111111"},
            {"type": "span", "text": cfg["title_highlight"], "color": "#ff334b"},
            {"type": "span", "text": cfg["title_after"], "color": "#111111"},
        ]
    else:
        title_contents = [
            {"type": "span", "text": cfg["title_before"], "color": "#111111"},
        ]

    flex_dict = {
        "type": "bubble",
        "size": "kilo",
        "hero": {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {
                "type": "uri",
                "uri": liff_url
            }
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingTop": "16px",
            "paddingStart": "16px",
            "paddingEnd": "16px",
            "paddingBottom": "0px",
            "backgroundColor": "#ffffff",
            "contents": [
                {
                    "type": "text",
                    "size": "16px",
                    "weight": "bold",
                    "wrap": True,
                    "contents": title_contents
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingTop": "14px",
            "paddingStart": "12px",
            "paddingEnd": "12px",
            "paddingBottom": "12px",
            "backgroundColor": "#ffffff",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "height": "40px",
                    "cornerRadius": "8px",
                    "backgroundColor": "#ff334b",
                    "justifyContent": "center",
                    "action": {
                        "type": "uri",
                        "uri": liff_url
                    },
                    "contents": [
                        {
                            "type": "text",
                            "text": cfg["button"],
                            "color": "#ffffff",
                            "weight": "bold",
                            "size": "14px",
                            "align": "center"
                        }
                    ]
                }
            ]
        }
    }

    return FlexMessage(
        alt_text=cfg["alt_text"],
        contents=FlexContainer.from_dict(flex_dict)
    )


def build_flex_message(keyword: str, group_id: str = "", mention_uid: str = "") -> FlexMessage:
    """카테고리에 따라 적절한 Flex Message를 생성."""
    category = KEYWORD_CATEGORY.get(keyword.lower(), "general")

    if category == "birthday":
        lang = BIRTHDAY_KEYWORD_LANG.get(keyword.lower(), "ko")
        return build_birthday_flex_message(lang, group_id=group_id, mention_uid=mention_uid)

    if category in CATEGORY_CONFIG:
        lang = detect_keyword_lang(keyword)
        return build_category_flex_message(category, lang)

    liff_url = f"https://liff.line.me/{LIFF_ID}"

    flex_dict = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "🎉 축하 메시지 감지!",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#ffffff"
                }
            ],
            "backgroundColor": "#00B8E5",
            "paddingAll": "16px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "감지된 키워드:",
                            "size": "sm",
                            "color": "#888888",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": keyword,
                            "size": "sm",
                            "weight": "bold",
                            "color": "#00B8E5",
                            "flex": 1,
                            "wrap": True,
                            "margin": "sm"
                        }
                    ]
                },
                {
                    "type": "separator"
                },
                {
                    "type": "text",
                    "text": "친구에게 따뜻한 선물을 보내보는 건 어떨까요?",
                    "wrap": True,
                    "size": "md",
                    "color": "#333333"
                }
            ],
            "paddingAll": "16px"
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": "🎁 선물 랭킹 보기",
                        "uri": liff_url
                    },
                    "style": "primary",
                    "color": "#00B8E5",
                    "height": "sm"
                }
            ],
            "paddingAll": "12px"
        }
    }

    return FlexMessage(
        alt_text="친구에게 선물을 보내보세요! 🎁",
        contents=FlexContainer.from_dict(flex_dict)
    )


# ── Webhook 엔드포인트 ────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    text = event.message.text
    print(f"[MSG] received: {text!r}")
    keyword = detect_keyword(text)
    print(f"[MSG] keyword: {keyword!r}")

    # 그룹/룸 멤버 프로필 캐시
    source = event.source
    room_key = None
    if isinstance(source, GroupSource):
        room_key = source.group_id
        print(f"[SOURCE] GroupSource group_id={source.group_id!r}")
    elif isinstance(source, RoomSource):
        room_key = source.room_id
        print(f"[SOURCE] RoomSource room_id={source.room_id!r}")
    if room_key and source.user_id:
        try:
            with ApiClient(configuration) as api_client:
                api = MessagingApi(api_client)
                # 그룹/룸 전용 API 사용 → 봇 미친구 멤버도 조회 가능
                if isinstance(source, GroupSource):
                    profile = api.get_group_member_profile(source.group_id, source.user_id)
                elif isinstance(source, RoomSource):
                    profile = api.get_room_member_profile(source.room_id, source.user_id)
                else:
                    profile = api.get_profile(source.user_id)
            if room_key not in group_members_cache:
                group_members_cache[room_key] = {}
            group_members_cache[room_key][source.user_id] = {
                "name": profile.display_name,
                "img": profile.picture_url or "",
                "userId": source.user_id,
            }
            save_cache(group_members_cache)
        except Exception as e:
            print(f"[CACHE] profile fetch error: {e}")

    # 멘션(@태그) 유저 ID 추출
    mention_uid = ""
    try:
        if event.message.mention and event.message.mention.mentionees:
            for m in event.message.mention.mentionees:
                if getattr(m, 'type', '') == 'user' and getattr(m, 'user_id', ''):
                    mention_uid = m.user_id
                    break
    except Exception:
        pass
    print(f"[MSG] mention_uid: {mention_uid!r}")

    if keyword:
        try:
            flex_msg = build_flex_message(keyword, group_id=room_key or "", mention_uid=mention_uid)
            with ApiClient(configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_msg]
                    )
                )
            print("[MSG] reply sent OK")
        except Exception as e:
            print(f"[MSG] reply error: {e}")


@handler.add(MemberJoinedEvent)
def handle_member_joined(event):
    source = event.source
    room_key = None
    if isinstance(source, GroupSource):
        room_key = source.group_id
    elif isinstance(source, RoomSource):
        room_key = source.room_id
    if not room_key:
        return
    for member in event.joined.members:
        uid = member.user_id
        try:
            with ApiClient(configuration) as api_client:
                profile = MessagingApi(api_client).get_profile(uid)
            if room_key not in group_members_cache:
                group_members_cache[room_key] = {}
            group_members_cache[room_key][uid] = {
                "name": profile.display_name,
                "img": profile.picture_url or "",
                "userId": uid,
            }
            save_cache(group_members_cache)
            print(f"[JOIN] cached {profile.display_name} in {room_key}")
        except Exception as e:
            print(f"[JOIN] error: {e}")


# ── LIFF 페이지 ───────────────────────────────────────────────────────────────
@app.route("/liff", methods=["GET"])
def liff_page():
    # index.html 대신 바로 birthday 페이지로 서버사이드 리다이렉트
    # (JS 리다이렉트는 LINE에서 뒤로가기 버튼을 생성하므로 서버 리다이렉트 사용)
    qs = request.query_string.decode()
    target = "/liff/birthday" + ("?" + qs if qs else "")
    return redirect(target, 302)


@app.route("/liff/birthday", methods=["GET"])
def liff_birthday():
    resp = make_response(render_template("birthday_liff.html", liff_id=LIFF_ID))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ── LIFF 현재 사용자 등록 ─────────────────────────────────────────────────────
@app.route("/api/register-member", methods=["POST"])
def register_member():
    data = request.get_json(silent=True) or {}
    room_id = data.get("roomId", "").strip()
    user_id = data.get("userId", "").strip()
    name = data.get("name", "").strip()
    img = data.get("img", "").strip()
    if room_id and user_id and name:
        if room_id not in group_members_cache:
            group_members_cache[room_id] = {}
        group_members_cache[room_id][user_id] = {
            "name": name, "img": img, "userId": user_id
        }
        save_cache(group_members_cache)
        print(f"[REGISTER] {name} → {room_id}")
    return jsonify({"ok": True})


# ── LIFF 컨텍스트 디버그 ──────────────────────────────────────────────────────
@app.route("/api/debug-context", methods=["POST"])
def debug_context():
    data = request.get_json(silent=True) or {}
    print(f"[DEBUG CTX] {data}")
    return jsonify({"ok": True})


# ── 그룹/룸 멤버 목록 API ──────────────────────────────────────────────────────
@app.route("/api/group-members", methods=["GET"])
def group_members():
    room_id = request.args.get("roomId", "").strip()
    room_type = request.args.get("roomType", "group").strip()
    print(f"[API] group-members roomId={room_id!r} roomType={room_type!r}")

    if not room_id:
        return jsonify({"members": []})

    cached = group_members_cache.get(room_id, {})

    # LINE Messaging API로 전체 멤버 ID 조회
    import requests as req
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    all_ids = []
    next_token = None
    try:
        while True:
            if room_type == "room":
                url = f"https://api.line.me/v2/bot/room/{room_id}/members/ids"
            else:
                url = f"https://api.line.me/v2/bot/group/{room_id}/members/ids"
            params = {"start": next_token} if next_token else {}
            r = req.get(url, headers=headers, params=params)
            print(f"[API] LINE members/ids status={r.status_code}")
            if r.status_code != 200:
                break
            data = r.json()
            all_ids.extend(data.get("memberIds", []))
            next_token = data.get("next")
            if not next_token:
                break
    except Exception as e:
        print(f"[API] members/ids error: {e}")

    # 전체 멤버 ID 조회 실패 시 캐시만 반환
    if not all_ids:
        return jsonify({"members": list(cached.values())})

    # 캐시에 없는 멤버만 추가로 프로필 조회
    # get_profile() 대신 그룹/룸 전용 API 사용 → 봇 미친구 멤버도 조회 가능
    members = []
    updated = False
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        for uid in all_ids:
            if uid in cached:
                members.append(cached[uid])
            else:
                try:
                    if room_type == "room":
                        profile = api.get_room_member_profile(room_id, uid)
                    else:
                        profile = api.get_group_member_profile(room_id, uid)
                    member = {
                        "name": profile.display_name,
                        "img": profile.picture_url or "",
                        "userId": uid,
                    }
                    members.append(member)
                    cached[uid] = member
                    updated = True
                except Exception:
                    continue

    if updated:
        group_members_cache[room_id] = cached
        save_cache(group_members_cache)

    print(f"[API] returned {len(members)} members")
    return jsonify({"members": members})


# ── 헬스체크 ─────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return "LINE Gift Bot is running! 🎁"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

#!/usr/bin/env python3
"""
Fetch top 16 products per category from LINE Gift Shop (TWD ≤ 600).
Score = LINE popularity 60% + Google Trends keyword match 40%

Trends 방식:
  - 카테고리 키워드로 related_queries 호출 (카테고리당 1회)
  - 급상승(rising) + 상위(top) 검색어 목록 수집
  - 각 상품 이름/브랜드에 해당 키워드 포함 시 가중치 부여

Outputs:
  static/data/top16_cake.json
  static/data/top16_coffee.json
  static/data/top16_beauty.json
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "static" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 카테고리 설정 ────────────────────────────────────────────────────────────
CATEGORIES = {
    "cake": {
        "apis": ["https://giftshop-tw.line.me/api/delivery-categories/2046697/products"],
        "output": DATA_DIR / "top16_cake.json",
        "trends_keywords": ["蛋糕", "甜點", "禮盒"],
    },
    "coffee": {
        "apis": [
            "https://giftshop-tw.line.me/api/voucher-categories/2024067/products",
            "https://giftshop-tw.line.me/api/delivery-categories/2024649/products",
        ],
        "output": DATA_DIR / "top16_coffee.json",
        "trends_keywords": ["咖啡", "手搖飲", "飲料"],
    },
    "beauty": {
        "apis": ["https://giftshop-tw.line.me/api/delivery-categories/2024644/products"],
        "output": DATA_DIR / "top16_beauty.json",
        "trends_keywords": ["保養", "護膚", "彩妝"],
    },
}

PRICE_LIMIT = 600  # TWD
PARAMS = {"sortType": "POPULARITY_DESC", "pageSize": 100}


def build_headers() -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Referer": "https://giftshop-tw.line.me/",
        "Origin": "https://giftshop-tw.line.me",
    }
    cookie = os.environ.get("LINE_COOKIE")
    csrf = os.environ.get("LINE_CSRF_TOKEN")
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Csrf-Token"] = csrf
    return headers


def fetch_products(api_url: str) -> list[dict]:
    resp = requests.get(api_url, params=PARAMS, headers=build_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", {})
    product_list = (
        result.get("pagedProducts", {}).get("content")
        or result.get("productList")
        or data.get("productList")
        or data.get("products")
        or []
    )
    if not product_list and isinstance(data, list):
        product_list = data
    return product_list


def filter_products(products: list[dict]) -> list[dict]:
    return [
        p for p in products
        if p.get("salePrice", 9999) <= PRICE_LIMIT
        and p.get("productStatusType") == "SALE"
        and not p.get("soldout", False)
    ]


def normalize(values: list[float]) -> list[float]:
    if not values:
        return values
    lo, hi = min(values), max(values)
    if hi == lo:
        return [100.0] * len(values)
    return [(v - lo) / (hi - lo) * 100 for v in values]


def fetch_trend_keywords(pytrends, keywords: list[str]) -> dict[str, float]:
    """
    카테고리 키워드로 Google Trends related_queries 호출.
    급상승(rising) 키워드는 2배 가중치.
    반환: {keyword: weight} — 상품명 매칭에 사용
    """
    trend_kw: dict[str, float] = {}
    try:
        pytrends.build_payload(keywords, geo="TW", timeframe="now 7-d")
        time.sleep(2)
        related = pytrends.related_queries()

        for kw in keywords:
            data = related.get(kw, {})

            # 상위 검색어 (top) — 가중치 1.0
            top_df = data.get("top")
            if top_df is not None and not top_df.empty:
                for _, row in top_df.iterrows():
                    query = str(row.get("query", "")).strip()
                    val = float(row.get("value", 0))
                    if query:
                        trend_kw[query] = max(trend_kw.get(query, 0), val * 1.0)

            # 급상승 검색어 (rising) — 가중치 2.0 (더 중요)
            rising_df = data.get("rising")
            if rising_df is not None and not rising_df.empty:
                for _, row in rising_df.iterrows():
                    query = str(row.get("query", "")).strip()
                    val = float(row.get("value", 0))
                    if query:
                        trend_kw[query] = max(trend_kw.get(query, 0), val * 2.0)

        print(f"  → 트렌드 키워드 {len(trend_kw)}개 수집")
        if trend_kw:
            top5 = sorted(trend_kw.items(), key=lambda x: x[1], reverse=True)[:5]
            print(f"  → 상위 5개: {top5}")
    except Exception as e:
        print(f"  [warn] Trends 실패: {e}")

    return trend_kw


def calc_trends_scores(products: list[dict], trend_kw: dict[str, float]) -> list[float]:
    """
    각 상품의 이름+브랜드에 트렌드 키워드가 포함되면 점수 부여.
    """
    if not trend_kw:
        return [0.0] * len(products)

    raw_scores = []
    for p in products:
        text = (p.get("productName", "") + " " + p.get("brandName", "")).lower()
        score = 0.0
        for kw, weight in trend_kw.items():
            if kw.lower() in text:
                score += weight
        raw_scores.append(score)

    return normalize(raw_scores)


def build_top16(products: list[dict], trend_kw: dict[str, float]) -> list[dict]:
    line_scores = normalize([
        float(p.get("recentSaleCount") or p.get("popularity") or 0)
        for p in products
    ])
    trends_scores = calc_trends_scores(products, trend_kw)

    scored = []
    for p, ls, ts in zip(products, line_scores, trends_scores):
        seller = p.get("simpleSeller") or {}
        scored.append({
            "id": p.get("id"),
            "brand": p.get("brandName", ""),
            "name": p.get("productName", ""),
            "price": p.get("displaySalePrice", f"${p.get('salePrice', '')}"),
            "img": p.get("representativeImageUrl", ""),
            "shopUrl": seller.get("shopUrl", ""),
            "lineScore": round(ls, 2),
            "trendsScore": round(ts, 2),
            "totalScore": round(ls * 0.4 + ts * 0.6, 2),
        })

    scored.sort(key=lambda x: x["totalScore"], reverse=True)

    # 브랜드별 최대 3개 제한
    brand_count: dict[str, int] = {}
    deduped = []
    for item in scored:
        if brand_count.get(item["brand"], 0) < 3:
            brand_count[item["brand"]] = brand_count.get(item["brand"], 0) + 1
            deduped.append(item)
        if len(deduped) == 16:
            break

    # 16개 미달 시 브랜드 제한 없이 인기순으로 나머지 채움
    if len(deduped) < 16:
        added_ids = {p["id"] for p in deduped}
        for item in scored:
            if item["id"] not in added_ids:
                deduped.append(item)
                added_ids.add(item["id"])
            if len(deduped) == 16:
                break

    return deduped


def process_category(name: str, cfg: dict, pytrends) -> None:
    print(f"\n{'='*50}")
    print(f"[{name.upper()}]")
    print(f"{'='*50}")

    # 1. 상품 수집
    print("[1/3] Fetching products…")
    raw = []
    seen_ids: set = set()
    for api_url in cfg["apis"]:
        for p in fetch_products(api_url):
            if p.get("id") not in seen_ids:
                seen_ids.add(p.get("id"))
                raw.append(p)
    print(f"  → {len(raw)} products received")

    filtered = filter_products(raw)
    print(f"[2/3] Filtering → {len(filtered)} products (price ≤ {PRICE_LIMIT})")

    if not filtered:
        print("[!] No products — skipping")
        return

    # 2. Google Trends 키워드 매칭
    print("[3/3] Google Trends keyword matching…")
    trend_kw: dict[str, float] = {}
    if pytrends and cfg.get("trends_keywords"):
        trend_kw = fetch_trend_keywords(pytrends, cfg["trends_keywords"])

    # 3. 순위 산정 & 저장
    top16 = build_top16(filtered, trend_kw)

    output = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trendKeywords": sorted(trend_kw, key=trend_kw.get, reverse=True)[:10],
        "products": top16,
    }
    with open(cfg["output"], "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(top16)} products → {cfg['output']}")
    for i, p in enumerate(top16, 1):
        print(f"  {i:2}. [L:{p['lineScore']:5.1f} T:{p['trendsScore']:5.1f} →{p['totalScore']:5.1f}]"
              f" {p['brand']} — {p['price']} — {p['name'][:35]}")


def main():
    pytrends = None
    try:
        from pytrends.request import TrendReq  # type: ignore
        pytrends = TrendReq(hl="zh-TW", tz=-480)
        print("pytrends 초기화 완료")
    except ImportError:
        print("[warn] pytrends not installed — trends scores = 0")
    except Exception as e:
        print(f"[warn] pytrends init failed: {e}")

    for name, cfg in CATEGORIES.items():
        process_category(name, cfg, pytrends)
        time.sleep(3)  # 카테고리 간 딜레이


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fetch top 16 cake/dessert products from LINE Gift Shop (TWD ≤ 600)
and score them using LINE popularity + Google Trends.

Output: static/data/top16.json
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "static" / "data" / "top16.json"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# ── LINE Gift Shop API ──────────────────────────────────────────────────────
CATEGORY_ID = "2046697"          # 케이크/디저트 카테고리
API_URL = (
    f"https://giftshop-tw.line.me/api/delivery-categories/{CATEGORY_ID}/products"
)
PARAMS = {
    "sortType": "POPULARITY_DESC",
    "pageSize": 100,
}

PRICE_LIMIT = 600  # TWD


def build_headers() -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
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


def fetch_products() -> list[dict]:
    print("[1/4] Fetching products from LINE Gift Shop…")
    resp = requests.get(API_URL, params=PARAMS, headers=build_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # 응답 구조: {"result": {"pagedProducts": {"content": [...]}}}
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

    print(f"  → {len(product_list)} products received")
    return product_list


def filter_products(products: list[dict]) -> list[dict]:
    print("[2/4] Filtering (price ≤ 600, on-sale, in-stock)…")
    filtered = [
        p for p in products
        if p.get("salePrice", 9999) <= PRICE_LIMIT
        and p.get("productStatusType") == "SALE"
        and not p.get("soldout", False)
    ]
    print(f"  → {len(filtered)} products after filter")
    return filtered


def normalize(values: list[float]) -> list[float]:
    if not values:
        return values
    lo, hi = min(values), max(values)
    if hi == lo:
        return [100.0] * len(values)
    return [(v - lo) / (hi - lo) * 100 for v in values]


def calc_line_scores(products: list[dict]) -> list[float]:
    raw = [float(p.get("recentSaleCount") or p.get("popularity") or 0) for p in products]
    return normalize(raw)


def calc_trends_scores(products: list[dict]) -> list[float]:
    print("[3/4] Fetching Google Trends scores…")
    scores = [0.0] * len(products)
    try:
        from pytrends.request import TrendReq  # type: ignore

        pytrends = TrendReq(hl="zh-TW", tz=-480)
        # 브랜드명 deduplicate
        brands = [p.get("brandName", "") for p in products]
        unique_brands = list(dict.fromkeys(b for b in brands if b))

        brand_score: dict[str, float] = {}
        # pytrends는 한 번에 최대 5개
        for i in range(0, len(unique_brands), 5):
            chunk = unique_brands[i : i + 5]
            try:
                pytrends.build_payload(chunk, geo="TW", timeframe="today 3-m")
                df = pytrends.interest_over_time()
                if not df.empty:
                    for brand in chunk:
                        if brand in df.columns:
                            brand_score[brand] = float(df[brand].mean())
                        else:
                            brand_score[brand] = 0.0
                else:
                    for brand in chunk:
                        brand_score[brand] = 0.0
            except Exception as e:
                print(f"  [warn] Trends chunk {chunk}: {e}")
                for brand in chunk:
                    brand_score[brand] = 0.0
            time.sleep(2)

        raw = [brand_score.get(p.get("brandName", ""), 0.0) for p in products]
        scores = normalize(raw)
        print(f"  → Trends fetched for {len(unique_brands)} brands")
    except ImportError:
        print("  [warn] pytrends not installed — trends scores = 0")
    except Exception as e:
        print(f"  [warn] Trends failed: {e} — trends scores = 0")
    return scores


def build_top16(products: list[dict]) -> list[dict]:
    line_scores = calc_line_scores(products)
    trends_scores = calc_trends_scores(products)

    print("[4/4] Ranking and selecting top 16…")
    scored = []
    for p, ls, ts in zip(products, line_scores, trends_scores):
        total = round(ls * 0.6 + ts * 0.4, 2)
        seller = p.get("simpleSeller") or {}
        scored.append(
            {
                "id": p.get("id"),
                "brand": p.get("brandName", ""),
                "name": p.get("productName", ""),
                "price": p.get("displaySalePrice", f"${p.get('salePrice', '')}"),
                "img": p.get("representativeImageUrl", ""),
                "shopUrl": seller.get("shopUrl", ""),
                "lineScore": round(ls, 2),
                "trendsScore": round(ts, 2),
                "totalScore": total,
            }
        )

    scored.sort(key=lambda x: x["totalScore"], reverse=True)
    return scored[:16]


def main():
    raw = fetch_products()
    filtered = filter_products(raw)

    if not filtered:
        print("[!] No products after filtering — aborting to keep previous data intact")
        return

    top16 = build_top16(filtered)

    output = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "products": top16,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(top16)} products → {OUTPUT}")
    for i, p in enumerate(top16, 1):
        print(f"  {i:2}. [{p['totalScore']:5.1f}] {p['brand']} — {p['price']} — {p['name'][:40]}")


if __name__ == "__main__":
    main()

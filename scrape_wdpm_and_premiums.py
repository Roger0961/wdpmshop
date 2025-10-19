# scrape_wdpm_and_premiums.py
import os, re, json, math
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import pandas as pd
from bs4 import BeautifulSoup

TAIPEI = ZoneInfo("Asia/Taipei")

TBOC_URL = "https://rate.bot.com.tw/gold/quote/recent"
WDPM_URL = "https://wdpmshop.com.tw/shop/"

# 追蹤的品項（品牌關鍵字, 克數, 顯示用標籤）
PRODUCTS = [
    # PAMP Lady Fortuna
    ("PAMP|財富女神", 1.0, "PAMP 財富女神 1g"),
    ("PAMP|財富女神", 2.5, "PAMP 財富女神 2.5g"),
    ("PAMP|財富女神", 5.0, "PAMP 財富女神 5g"),
    ("PAMP|財富女神", 10.0, "PAMP 財富女神 10g"),
    ("PAMP|財富女神", 20.0, "PAMP 財富女神 20g"),
    ("PAMP|財富女神", 50.0, "PAMP 財富女神 50g"),
    ("PAMP|財富女神", 100.0, "PAMP 財富女神 100g"),
    ("PAMP|財富女神", 15.5517, "PAMP 財富女神 0.5oz"),
    ("PAMP|財富女神", 31.1035, "PAMP 財富女神 1oz"),
    # Perth Mint
    ("Perth|伯斯|天鵝", 1.0, "Perth Mint 1g"),
    ("Perth|伯斯|天鵝", 5.0, "Perth Mint 5g"),
    ("Perth|伯斯|天鵝", 31.1035, "Perth Mint 1oz"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PremiumBot/1.0; +github-actions)"}

def load_tboc_from_local():
    p = "data/tboc_goldpassbook.json"
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            j = json.load(f)
            return float(j["price_twd_per_gram"])
    return None

def fetch_tboc_fallback():
    # 保險：若本地 JSON 不在，直接抓
    tables = pd.read_html(TBOC_URL)
    gram_sell = None
    for df in tables:
        df.columns = [str(c).strip() for c in df.columns]
        for i in range(len(df)):
            row_text = " ".join(str(x) for x in df.iloc[i].values)
            if ("存摺" in row_text) and ("公克" in row_text) and ("1" in row_text):
                for col in df.columns:
                    if "賣出" in str(col):
                        m = re.search(r"[\d,]+(?:\.\d+)?", str(df.loc[i, col]))
                        if m:
                            gram_sell = float(m.group(0).replace(",", ""))
                            break
            if gram_sell: break
        if gram_sell: break
    if gram_sell is None:
        raise RuntimeError("抓台銀 1g 賣出價失敗（fallback）。")
    return gram_sell

def grams_patterns(g):
    pats = []
    if math.isclose(g, 31.1035, rel_tol=1e-3):
        pats += [r"\b1\s*oz\b", r"1\s*盎司", r"一盎司"]
    elif math.isclose(g, 15.5517, rel_tol=1e-3):
        pats += [r"0\.5\s*oz", r"半盎司", r"0\.5\s*盎司"]
    else:
        g_int = int(round(g))
        pats += [fr"\b{g_int}\s*g\b", fr"{g_int}\s*公克"]
    return pats

def fetch_wdpm_prices():
    html = requests.get(WDPM_URL, headers=HEADERS, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    texts = [t.strip() for t in soup.find_all(string=True) if t and t.strip()]
    lines = [l for l in texts if l]
    # 在每一行的上下文尋找價格與關鍵字
    candidates = []
    for i, line in enumerate(lines):
        ctx = " ".join(lines[max(0, i-2): i+3])
        # 價格（整數可能帶逗號）
        prices = re.findall(r"(?:NT\$|＄|\$)?\s*([1-9]\d{2,}(?:,\d{3})*)\s*(?:元)?", ctx)
        if prices:
            candidates.append((ctx, max(int(p.replace(",", "")) for p in prices)))
    # 逐品項比對
    results = []
    for brand_regex, grams, label in PRODUCTS:
        gram_pats = grams_patterns(grams)
        price_found, ctx_found = None, None
        for ctx, price in candidates:
            if re.search(brand_regex, ctx, flags=re.I):
                if any(re.search(p, ctx, flags=re.I) for p in gram_pats):
                    price_found, ctx_found = price, ctx[:160]
                    break
        if price_found:
            results.append({"label": label, "grams": grams, "retail_price_twd": price_found, "context": ctx_found})
    return results

def main():
    tboc = load_tboc_from_local()
    if tboc is None:
        tboc = fetch_tboc_fallback()

    items = fetch_wdpm_prices()
    out = []
    for it in items:
        base = tboc * it["grams"]
        premium = it["retail_price_twd"] - base
        pct = premium / base * 100 if base > 0 else None
        out.append({
            "label": it["label"],
            "grams": round(it["grams"], 4),
            "retail_price_twd": it["retail_price_twd"],
            "tboc_base_twd": round(base, 2),
            "premium_twd": round(premium, 2),
            "premium_pct": round(pct, 3) if pct is not None else None
        })
    out.sort(key=lambda x: (x["label"]))

    payload = {
        "timestamp_taipei": datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S"),
        "source": {"tboc": TBOC_URL, "wdpm": WDPM_URL},
        "tboc_gram_sell": tboc,
        "items": out
    }
    os.makedirs("data", exist_ok=True)
    with open("data/premiums.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("DONE premiums", len(out), "items")

if __name__ == "__main__":
    main()

# scrape_tboc.py
import os, re, json, time, csv
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import pandas as pd
from bs4 import BeautifulSoup

TAIPEI = ZoneInfo("Asia/Taipei")
URL = "https://rate.bot.com.tw/gold/quote/recent"

def extract_with_pandas(url):
    tables = pd.read_html(url)
    # 在所有表格裡找同時包含「存摺」「1」「公克」的列，並讀取「賣出」欄
    for df in tables:
        df.columns = [str(c).strip() for c in df.columns]
        for i in range(len(df)):
            row_text = " ".join(str(x) for x in df.iloc[i].values)
            if ("存摺" in row_text) and ("公克" in row_text) and ("1" in row_text):
                for col in df.columns:
                    if "賣出" in str(col):
                        val = df.loc[i, col]
                        m = re.search(r"[\d,]+(?:\.\d+)?", str(val))
                        if m:
                            return float(m.group(0).replace(",", ""))
    return None

def extract_with_bs4(url):
    html = requests.get(url, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    # 找包含價格的表格文字區塊
    texts = [t.strip() for t in soup.find_all(string=True) if t and t.strip()]
    # 尋找包含關鍵字的近鄰行
    for idx, line in enumerate(texts):
        ctx = " ".join(texts[max(0, idx-3): idx+4])
        if ("存摺" in ctx) and (re.search(r"\b1\s*公克\b", ctx) or "1公克" in ctx) and ("賣出" in ctx):
            # 抓同一上下文中的最大數字
            nums = re.findall(r"[1-9]\d{2,}(?:,\d{3})*(?:\.\d+)?", ctx)
            if nums:
                vals = [float(n.replace(",", "")) for n in nums]
                # 價格通常在數千～數萬範圍，挑合理區間
                cand = [v for v in vals if 1000 <= v <= 10000]
                if cand:
                    return max(cand)
    return None

def main():
    price = extract_with_pandas(URL)
    if price is None:
        price = extract_with_bs4(URL)
    if price is None:
        raise SystemExit("找不到『台銀黃金存摺 1 公克 賣出價』，請檢查頁面是否改版。")

    now = datetime.now(TAIPEI)
    payload = {
        "timestamp_taipei": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": URL,
        "product": "台灣銀行 黃金存摺 1 公克 賣出",
        "price_twd_per_gram": round(price, 2)
    }

    os.makedirs("data", exist_ok=True)
    with open("data/tboc_goldpassbook.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 追加歷史紀錄
    hist_path = "data/history.csv"
    new_row = [payload["timestamp_taipei"], payload["price_twd_per_gram"]]
    write_header = not os.path.exists(hist_path)
    with open(hist_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp_taipei", "price_twd_per_gram"])
        w.writerow(new_row)

    print("OK", payload)

if __name__ == "__main__":
    main()

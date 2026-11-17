import json
import os
import re
import time
from datetime import datetime
import feedparser
import requests
from bs4 import BeautifulSoup

RSS_FEEDS = {
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "Sky Sports": "https://www.skysports.com/rss/12040",
    "The Guardian": "https://www.theguardian.com/football/rss",
    "ESPN FC": "https://www.espn.com/espn/rss/soccer/news"
}

DATA_FILE = "news.json"
MAX_NEWS_TOTAL = 50
MAX_NEW_PER_SOURCE = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

DEFAULT_IMAGE = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?auto=format&fit=crop&w=800&q=80"

def is_persian(text):
    return bool(re.search(r'[\u0600-\u06FF]', text or ""))

def translate_to_persian(text):
    if not text or not text.strip():
        return ""
    text = text.strip()[:2500]
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "en",
        "tl": "fa",
        "dt": "t",
        "q": text
    }
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json()
            translated = "".join([part[0] for part in data[0] if part[0]])
            return translated.strip()
    except Exception as e:
        print(f"Translate API error: {e}")
    return ""

def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return re.sub(r'\s+', ' ', soup.get_text(separator=" ", strip=True))

def scrape_full_article(url, fallback_summary, fallback_img):
    paragraphs = []
    hd_image = fallback_img
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # استخراج تصویر باکیفیت اصلی خبر (og:image)
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                hd_image = og_img["content"]

            # حذف بخش‌های تبلیغاتی و منوها
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()

            article_body = soup.find("article") or soup.find("main") or soup
            for p in article_body.find_all("p"):
                txt = re.sub(r'\s+', ' ', p.get_text(strip=True))
                # فیلتر کردن جملات کوتاه تبلیغاتی یا کپی‌رایت
                if len(txt) > 65 and not any(skip in txt.lower() for skip in ["cookie", "subscribe", "newsletter", "all rights reserved", "follow us"]):
                    if txt not in paragraphs:
                        paragraphs.append(txt)
                if len(paragraphs) >= 8:
                    break
    except Exception as e:
        print(f"Scrape error for {url}: {e}")

    if not paragraphs and fallback_summary:
        paragraphs = [fallback_summary]

    return paragraphs, hd_image

def extract_rss_image(entry):
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0]['url']
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    return DEFAULT_IMAGE

def main():
    existing_news = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # نگه‌داشتن فقط اخباری که واقعاً فارسی هستند و متن کامل دارند
                existing_news = [
                    item for item in loaded
                    if is_persian(item.get("title", "")) and item.get("content")
                ]
        except Exception:
            existing_news = []

    existing_links = {item["link"] for item in existing_news}
    new_items = []

    for source_name, feed_url in RSS_FEEDS.items():
        print(f"Fetching from {source_name}...")
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                if count >= MAX_NEW_PER_SOURCE:
                    break

                link = entry.get("link", "")
                if not link or link in existing_links:
                    continue

                orig_title = clean_html(entry.get("title", ""))
                orig_summary = clean_html(entry.get("summary", ""))
                if not orig_title:
                    continue

                # استخراج متن کامل خبر از صفحه اصلی سایت
                rss_img = extract_rss_image(entry)
                en_paragraphs, best_image = scrape_full_article(link, orig_summary, rss_img)

                # ترجمه تیتر به فارسی
                fa_title = translate_to_persian(orig_title)
                if not is_persian(fa_title):
                    continue

                # ترجمه خلاصه و کل پاراگراف‌های مقاله به فارسی
                full_en_text = "\n\n".join(en_paragraphs)
                fa_full_text = translate_to_persian(full_en_text)
                
                fa_paragraphs = [p.strip() for p in fa_full_text.split("\n") if len(p.strip()) > 20]
                if not fa_paragraphs:
                    fa_summary_fallback = translate_to_persian(orig_summary)
                    if is_persian(fa_summary_fallback):
                        fa_paragraphs = [fa_summary_fallback]
                    else:
                        continue

                fa_summary = fa_paragraphs[0][:220] + "..." if len(fa_paragraphs[0]) > 220 else fa_paragraphs[0]

                news_obj = {
                    "source": source_name,
                    "title": fa_title,
                    "summary": fa_summary,
                    "content": fa_paragraphs,
                    "link": link,
                    "image": best_image,
                    "published": entry.get("published", datetime.utcnow().strftime("%Y-%m-%d %H:%M")),
                    "timestamp": datetime.utcnow().isoformat()
                }

                new_items.append(news_obj)
                existing_links.add(link)
                count += 1
                time.sleep(0.5)
        except Exception as e:
            print(f"Error parsing {source_name}: {e}")

    updated_news = new_items + existing_news
    updated_news = updated_news[:MAX_NEWS_TOTAL]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_news, f, ensure_ascii=False, indent=2)

    print(f"Successfully saved {len(updated_news)} Persian full-text articles.")

if __name__ == "__main__":
    main()

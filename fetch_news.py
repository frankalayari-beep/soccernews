import json
import os
import re
from datetime import datetime
import feedparser
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# منابع خبری معتبر دنیای فوتبال
RSS_FEEDS = {
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "Sky Sports": "https://www.skysports.com/rss/12040",
    "ESPN FC": "https://www.espn.com/espn/rss/soccer/news",
    "The Guardian": "https://www.theguardian.com/football/rss"
}

DATA_FILE = "news.json"
MAX_NEWS_TOTAL = 60
MAX_NEW_PER_SOURCE = 5

# تصویر پیش‌فرض در صورتی که خبر فاقد عکس باشد
DEFAULT_IMAGE = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?auto=format&fit=crop&w=800&q=80"

def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r'\s+', ' ', text)

def extract_image(entry):
    # بررسی تگ‌های استاندارد رسانه در RSS
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0]['url']
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    if 'links' in entry:
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                return link.get('href')
    # جستجوی تگ img در توضیحات خبر
    summary = entry.get('summary', '')
    soup = BeautifulSoup(summary, "html.parser")
    img_tag = soup.find('img')
    if img_tag and img_tag.get('src'):
        return img_tag.get('src')
    return DEFAULT_IMAGE

def translate_text(text, translator):
    if not text:
        return ""
    try:
        # محدود کردن طول متن برای جلوگیری از خطای مترجم
        return translator.translate(text[:450])
    except Exception as e:
        print(f"Translation error: {e}")
        return text

def main():
    translator = GoogleTranslator(source='auto', target='fa')
    
    # بارگذاری اخبار قبلی برای جلوگیری از ترجمه تکراری
    existing_news = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing_news = json.load(f)
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

                fa_title = translate_text(orig_title, translator)
                fa_summary = translate_text(orig_summary, translator)
                image_url = extract_image(entry)

                news_obj = {
                    "source": source_name,
                    "title": fa_title,
                    "original_title": orig_title,
                    "summary": fa_summary,
                    "link": link,
                    "image": image_url,
                    "published": entry.get("published", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")),
                    "timestamp": datetime.utcnow().isoformat()
                }

                new_items.append(news_obj)
                existing_links.add(link)
                count += 1
        except Exception as e:
            print(f"Error parsing {source_name}: {e}")

    # ترکیب اخبار جدید در صدر لیست و حفظ سقف مجاز
    updated_news = new_items + existing_news
    updated_news = updated_news[:MAX_NEWS_TOTAL]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_news, f, ensure_ascii=False, indent=2)

    print(f"Added {len(new_items)} new articles. Total stored: {len(updated_news)}")

if __name__ == "__main__":
    main()

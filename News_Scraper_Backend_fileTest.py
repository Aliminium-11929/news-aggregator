import os
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import threading
import feedparser
import csv
from deep_translator import GoogleTranslator

feed_url = "https://almanar.com.lb/rss"
feed = feedparser.parse(feed_url)

def translate_text(text, target_language):
    """
    Translates the given text into the target language using deep-translator.
    
    Parameters:
        text (str): The text to translate.
        target_language (str): The target language code (e.g., 'en' for English, 'fr' for French).
    
    Returns:
        str: Translated text.
    """
    return GoogleTranslator(source='auto', target=target_language).translate(text)

def threaded_get_feed(entry,Arr,i,lang):
    try:
        lang=lang.lower()
        ISO_language={
            "arabic": "ar",
            "french": "fr",
            "english": "en",
            "spanish": "es",
            "german": "de",
            "chinese (simplified)": "zh-CN",
            "chinese (traditional)": "zh-TW",
            "japanese": "ja",
            "russian": "ru",
        }
        title = entry.title
        link = entry.link
        published = entry.published
        A={}
        A['title']=translate_text(title,ISO_language[lang])
        A['link']=link
        A['published']=published
        response = requests.get(link, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        article_content = soup.find("div", class_="article-content")

        if not article_content:
            output_text=(f"No content to be displayed.")
            A['content']=translate_text(output_text,ISO_language[lang])
            Arr[i]=A
            return
        text = article_content.get_text(strip=True, separator="\n")
        if text:
            summary = gemini_summary(text,lang)
            if summary:
                A['content']=summary
                Arr[i]=A
        else:
            output_text=(f"No content to be displayed.")
            A['content']=translate_text(output_text,ISO_language[lang])
            Arr[i]=A
    except Exception as e:
        Arr[i] = {
            "title": translate_text("Error occurred",ISO_language[lang]),
            "link": "N/A",
            "published": "N/A",
            "content": translate_text(f"An error occurred: {e}",ISO_language[lang]),
        }

# Google Gemini query function
def gemini_summary(prompt,language):
    load_dotenv()
    google_gemini_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
    if not google_gemini_api_key:
        raise ValueError("Google Gemini API key not set. Check your .env file.")
    prompt = f"Summarize briefly in {language} the following news:\n {prompt}"
    url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": google_gemini_api_key}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }

    try:
        response = requests.post(url, headers=headers, params=params, json=payload, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        result = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No response content found.")
        return result
    except requests.exceptions.RequestException as e:
        print("Error", f"An error occurred: {e}")
        return None
    
def get_feed(lang):
    Arr=["","","","",""]
    i=0
    threads = []
    for i, entry in enumerate(feed.entries[:5]):
        thread = threading.Thread(target=threaded_get_feed, args=(entry, Arr, i, lang))
        threads.append(thread)
        thread.start()
    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    return Arr

arr=get_feed("arabic")

with open("News.csv",'w', encoding='utf-8') as f:
    fields=['title','link','published','content']
    csv_writer=csv.DictWriter(f,fieldnames=fields,delimiter='|')
    csv_writer.writeheader()
    for article in arr:
        csv_writer.writerow(article)
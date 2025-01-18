import os
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import threading
import feedparser

feed_url = "https://almanar.com.lb/rss"
feed = feedparser.parse(feed_url)


def threaded_get_feed(entry,Arr,i):
    try:
        title = entry.title
        link = entry.link
        published = entry.published

        response = requests.get(link, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        article_content = soup.find("div", class_="article-content")

        if not article_content:
            output_text=(f"Title: {title}\nLink: {link}\nPublished: {published}\n{'-' * 80}\n")
            Arr[i]=output_text
            return
        text = article_content.get_text(strip=True, separator="\n")
        if text:
            summary = gemini_summary(text)
            if summary:
                output_text=(f"Title: {title}\nLink: {link}\nPublished: {published}\n")
                output_text+=(f"Summary:\n{summary}\n{'-' * 80}\n")
                Arr[i]=output_text
        else:
            output_text=(f"Title: {title}\nLink: {link}\nPublished: {published}\n{'-' * 80}\n")
            Arr[i]=output_text
    except Exception as e:
        output_text=(f"An error occurred: {e}\n{'-' * 80}\n")
        Arr[i]=output_text

# Google Gemini query function
def gemini_summary(prompt):
    load_dotenv()
    google_gemini_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
    if not google_gemini_api_key:
        raise ValueError("Google Gemini API key not set. Check your .env file.")
    prompt = f"Summarize briefly in arabic the following news:\n {prompt}"
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

def get_feed():
    Arr=["","","","",""]
    i=0
    threads = []
    for i, entry in enumerate(feed.entries[:5]):
        thread = threading.Thread(target=threaded_get_feed, args=(entry, Arr, i))
        threads.append(thread)
        thread.start()
    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    return Arr

# arr=get_feed()
# output=""
# for s in arr:
#     output+=s
# print(output)
# with open("News.txt", "w", encoding="utf-8") as f:
#     f.write(output)

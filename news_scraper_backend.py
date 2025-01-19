import os
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import threading
import feedparser
import csv
from deep_translator import GoogleTranslator
from datetime import datetime, timezone
import os
#Dictionary to help in translating supproted languages
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

article_Dict={}

links={
    "almanar":"https://almanar.com.lb/rss",
    "aljadeed":"https://www.aljadeed.tv/Rss/latest-news",
}

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
            summary = gemini_call("summary",lang,text)
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
def gemini_call(cmd,language,text):
    load_dotenv()
    google_gemini_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
    if not google_gemini_api_key:
        raise ValueError("Google Gemini API key not set. Check your .env file.")
    cmd_Dict={
        "summary":f"Summarize briefly in {language} the following news:\n {text}",
        "vid_summary":f"Summarize briefly in {language} the news in the video at this link:\n {text}",
    }
    command = cmd_Dict[cmd]
    url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": google_gemini_api_key}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": command}]}],
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
    
def get_feed(lang,src):
    feed_url = links[src]
    feed = feedparser.parse(feed_url)
    Arr=["" for i in range(10)]
    i=0
    threads = []
    for i, entry in enumerate(feed.entries[:10]):
        thread = threading.Thread(target=threaded_get_feed, args=(entry, Arr, i, lang))
        threads.append(thread)
        thread.start()
    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    article_Dict[src]=Arr
    createCSV(src)

#Source being the name, and not the link, of the news organization
def createCSV(source):
    data_array = []
    #Set to check unique links as not to write the same news article twice into the CSV file
    already_exists=set()
    #Check if file initially exists
    name = source+".csv"
    if not os.path.exists(name):
        with open(name, 'w') as file:
            filler=""
    with open(name, "r" , encoding = 'utf-8') as f:
        reader = csv.reader(f, delimiter='Ξ')  
        i=0
        for row in reader:
            i+=1
            if i == 1 or not row:
                continue
            already_exists.add(row[1])
            # Create a dictionary for each row
            entry = {
                "title": row[0],
                "link": row[1],
                "published": row[2],
                "content": row[3]
            }
            data_array.append(entry)
    #Write to CSV file, the new and the old data
    with open(name,'w', encoding='utf-8') as f:
        fields=['title','link','published','content']
        csv_writer=csv.DictWriter(f,fieldnames=fields,delimiter='Ξ')
        csv_writer.writeheader()
        #Add the articles found into the total data_array
        for article in article_Dict[source]:
            if not (article["link"] in already_exists and article["link"] != "N/A"):
                data_array.append(article)
        #sort the array
        sorted_data = sorted(
            data_array,
            key=lambda x: datetime.strptime(x["published"], "%a, %d %b %Y %H:%M:%S %z")
            if x["published"] != "N/A" else datetime.min.replace(tzinfo=timezone.utc),
            reverse=True  # Decomment to sort in descending order (top-down by time)
        )

        for article in sorted_data:
            csv_writer.writerow(article)

# Testing:

# lang = "arabic"
# get_feed(lang,"almanar")

#The code runs as expected however, some aspects are currently hardcoded(as shown by later comments) due to the fact that we are only dealing 
#with 3 sources. Time format, and how to get certain data from non-RSS, are currently hard coded, however they can be easily fixed using dictionaries
#as we have done before. In addition, optimization of threading and adding a self deleting feature so that any article older than a week/whatever time unit
#we may choose may be automatically deleted from the CSV to conserve space.
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
import time
from dateutil import parser
import pandas as pd


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
#Future dictionary to help in storing the articles of each source for future writing in a CSV file
article_Dict={}
#Dictionary that takes source as key and the RSS feed link as value, we seperated it from the non_rss links due to having
#different ways to handle each of them.
rss_links={
    "almanar":"https://almanar.com.lb/rss",
    "aljadeed":"https://www.aljadeed.tv/Rss/latest-news",
}
#Dictionary that takes source as key and the backend API link as value in order to access the news feed directly
non_rss_api_url={
    "mtv":"https://vodapi.mtv.com.lb/api/Service/GetArticlesByNewsSectionID?id=1&start=0&end=20&keywordId=-1&onlyWithSource=false&type=&authorId=-1&platform=&isLatin=",
    
}
#Tells us what to search for in the html content of an article to find the actual cotnent of the article, since they differ from one source to the other.
content_loc={
    "mtv":("p","_pragraphs"),
    "almanar":("div","article-content"),
    "aljadeed":("div","LongDesc text-title-9"),
}

def process_time(input_time:datetime) -> str:
    dt_object = parser.parse(input_time)
    output_date = dt_object.strftime("%a, %d %b %Y %H:%M:%S +0000")
    return output_date

#Translates the given text into the target language using deep-translator
def translate_text(text: str, target_language: str) -> str:
    n=len(text)
    if n>5000:
        text_arr=text.split("\n")
        text=""
        for string in text_arr:
            text+= translate_text(string,target_language)+"\n"
    return GoogleTranslator(source='auto', target=target_language).translate(text)

#A thread that is used by both RSS and non-RSS sources to get a content summary
def thread_get_content(link:str, Article:dict, source_articles:list[dict], article_index:int, lang:str, src:str):
    try:
        response = requests.get(link, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        #Use the specific locaiton we need to get the actual content of the article after acquiring the link
        article_content = soup.find(content_loc[src][0], class_=content_loc[src][1])
        #Sets default content to No content if no text exists in the actual article(5abar 3ajel and reminder fro nashras etc.)
        if not article_content:
            output_text=(f"No content to be displayed.")
            Article['content']=translate_text(output_text,ISO_language[lang])
            Article['summary']=translate_text(f"Unavailable",ISO_language[lang])
            source_articles[article_index]=Article
            return
        text = article_content.get_text(strip=True, separator="\n")
        if text:
            Article['content']=translate_text(text,ISO_language[lang])
            if src=="aljadeed":
                Article['content']=Article["content"].replace("&quot;","\"")
            #Gemini call to summarize the content of the article
            summary = gemini_call("summary",lang,text,src)
            if summary:
                Article['summary']=summary
            else:
                Article['summary']=translate_text(f"Unavailable",ISO_language[lang])
            source_articles[article_index]=Article
        else:
            output_text=(f"No content to be displayed.")
            Article['content']=translate_text(output_text,ISO_language[lang])
            Article['summary']=translate_text(f"Unavailable",ISO_language[lang])
            source_articles[article_index]=Article
    except Exception as e:
        #Set link and other values as N/A where they will be filtered out later on, as in not displayed in the final result
        #In case of error, the future calls get the missed news.
        source_articles[article_index] = {
            "title": translate_text("Error occurred: ",ISO_language[lang])+str(e),
            "link": "Not Available",
            "published": "Not Available",
            "content": translate_text(f"Error occurred: ",ISO_language[lang])+str(e),
            "summary": translate_text(f"Unavailable",ISO_language[lang]),
        }
#In case RSS feed exists, we call this method to populate our Array "source_articles" with the article "Article" at index article_index
def threaded_get_feed(entry, source_articles: list[dict], article_index: int, lang: str, src: str, already_exists:set):
    try:
        lang=lang.lower()
        title = entry.title
        link = entry.link
        if link in already_exists:
            return
        published = process_time(entry.published)
        Article={}
        Article['title']=translate_text(title,ISO_language[lang])
        if src=="aljadeed":
            Article['title']=Article['title'].replace("&quot;","\"")
        Article['link']=link
        #Hard coded, will be fixed once we create a universal standardized time format using dateutil
        Article['published']=published
        thread_get_content(link,Article,source_articles,article_index,lang,src)
    #Error to auto-filter articles that experienced an error...
    except Exception as e:
        source_articles[article_index] = {
            "title": translate_text("Error occurred: ",ISO_language[lang])+str(e),
            "link": "Not Available",
            "published": "Not Available",
            "content": translate_text(f"Error occurred: ",ISO_language[lang])+str(e),
            "summary": translate_text(f"Unavailable",ISO_language[lang]),
        }
    
# Google Gemini query function
def gemini_call(cmd: str, language: str, text: str, src:str, more = "") -> str:
    n=len(text)
    load_dotenv()
    google_gemini_api_key = os.getenv("GOOGLE_GEMINI_API_KEY_"+src)
    if not google_gemini_api_key:
        raise ValueError("Google Gemini API key not set. Check your .env file.")
    #Different propmt for different services, such as video and text, and perhaps images in the future, no video summarization support exists yet
    cmd_Dict={
        "summary":f"Summarize briefly {more} in {language} the following news:\n {text}",
        "vid_summary":f"Summarize briefly in {language} the news in the video at this link:\n {text}",
    }
    #The structure and inputs of the function makes it very easy to have a centralized methods for all uses of this method to have gemini do a certain task
    prompt = cmd_Dict[cmd]
    if cmd=="summary" and n>4900:
        text_arr=text.split("\n") # split by paragraph
        for text in text_arr:
            if text == "":
                text_arr.remove("")  
        i = 0
        while i < len(text_arr) - 1:
            if len(text_arr[i]) + len(text_arr[i+1]) < 4900:
                text_arr[i] += text_arr[i+1]  # Merge current and next string
                del text_arr[i+1]  # Remove the merged element
            else:
                i += 1 
        text=""
        for string in text_arr:
            size = n/len(text_arr)
            text+=gemini_call(cmd,language,string,src, (",in strictly less than "+str(size)+" characters,"))+"\n"
        return gemini_call(cmd,language,text,src)
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
    #Printing as place holder for status code 404 once we implement fastAPI in case of error
    except requests.exceptions.RequestException as e:
        print("Error", f"An error occurred: {e}")
        return None
    
def get_feed(lang: str, src: str, article_count: int, already_exists:set, memory: list):
    # Cap max amount of articles to 14 retrieved articles in a single call, as we realistically cant get more from a single RSS
    # if article_count>14:
    #     article_count=14
    #     #Placeholder for future status code/may be removed as we are the one setting this number
    #     print("Number of requested articles is too large, automatically set to 14.")
    #Our main array, wil be an array of dictionaries where each dictionary is an article containing: link, title, publish date(as published), and content(using gemini to summarize)
    source_articles=[{} for i in range(article_count)]
    #Handle non-RSS seperately
    if src not in rss_links:
        fetch_articles(non_rss_api_url[src], source_articles, lang, src, article_count, already_exists, memory)
        return
    feed_url = rss_links[src]
    feed = feedparser.parse(feed_url)
    thread_index=0
    threads = []
    #Start a thread for each article as we populate the array, since we are accessing only a single index at max from all threads, it should be threadsafe
    for thread_index, entry in enumerate(feed.entries[:article_count]):
        thread = threading.Thread(target=threaded_get_feed, args=(entry, source_articles, thread_index, lang, src, already_exists))
        threads.append(thread)
        thread.start()
    # Wait for all threads to finish as to not preemptively use a semi-complete or empty source_articles to populate our CSV file
    for thread in threads:
        thread.join()
    
    article_Dict[src]=source_articles
    createCSV(src, already_exists, memory)

def get_existing_articles(source:str, data_array:list):
    already_exists=set()
    #Check if file initially exists
    name = source+".csv"
    if not os.path.exists(name):
        with open(name, 'w') as file:
            #useless line of code as to not get an error, probably can be changed to just opening the file.
            filler=""
    #Read from the CSV file to get the new "Overall" feed, including old and new
    with open(name, "r" , encoding = 'utf-8') as f:
        reader = csv.reader(f, delimiter=',')  
        row_index=0
        for row in reader:
            row_index+=1
            if row_index == 1 or not row:
                continue
            already_exists.add(row[1])
            # Create a dictionary for each row
            entry = {
                "title": row[0],
                "link": row[1],
                "published": row[2],
                "content": row[3],
                "summary": row[4]
            }
            #data_array is our total articles, the array we will use to write to the CSV file the total articles.
            data_array.append(entry)
    return already_exists


#Source being the name, and not the link, of the news organization, writes a CSV file of the total news sofar of a given news source
def createCSV(source: str,already_exists:set, data_array:list[dict]):
    #Write to CSV file, the new and the old data
    name = source+".csv"
    with open(name,'w', encoding='utf-8') as f:
        fields=['title','link','published','content','summary']
        csv_writer=csv.DictWriter(f,fieldnames=fields,delimiter=',')
        csv_writer.writeheader()
        #Add the articles found for a given source into the total data_array
        for article in article_Dict[source]:
            if article and article["link"] != "":
                data_array.append(article)
                already_exists.add(article["link"])
        #sort the array
        sorted_data = sorted(
            data_array,
            key=lambda x: datetime.strptime(x["published"], "%a, %d %b %Y %H:%M:%S %z")
            if x["published"] != "Not Available" else datetime.min.replace(tzinfo=timezone.utc),
            
            # Decomment the below line to sort in descending order (top-down by time)
            reverse=True  
        )
    #Write the data to the CSV file.
        for article in sorted_data:
            csv_writer.writerow(article)

#Helper function in order to allow threading when accessing and organizing articles
def fetch_helper(source_articles: list[dict], article_index:int, article:dict, lang:str, src:str):
    #Currently hard-coded time fixing, can be made into a global function by using datautil library.
    correctFormat = process_time(article["date"])
    thread_get_content(article["websiteUrl"],{},source_articles,article_index,lang,src)
    source_articles[article_index]=({"title": article["name"],
             "link": article["websiteUrl"],
             "published" : correctFormat,
             "content":source_articles[article_index]["content"],
             "summary":source_articles[article_index]["summary"]})
    
# Function to fetch and process the data
def fetch_articles(url:str, source_articles:list[dict], lang:str, src:str, article_count:int, already_exists:set,memory:list):
    try:
        # Send a GET request to the API
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON data
        data = response.json()
        # Extract articles and create a dictionary
        articles = data.get("articles", [])
        thread_index=0
        threads = []
        #Create a thread to handle each article seperately
        for thread_index, article in enumerate(articles):
            if thread_index>=article_count:
                break
            if article["websiteUrl"] in already_exists:
                continue
            thread = threading.Thread(target=fetch_helper, args=(source_articles, thread_index, article, lang, src))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        article_Dict[src]=source_articles
        createCSV(src,already_exists,memory)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

# A way to allow for the code to run and be stopped without halting the code, all the user has to do is input "n"
def get_user_input():
    global x
    x=""
    while not stop_event.is_set():
        user_input = input("Enter \"n\" at any time to stop at the next cycle.\n").strip()
        x = user_input
        if x == "n":
            break
    print("Program has been shut down.")
#A method that will help in creating a seperate thread fro each news source
def auto_get_feed(language: str, source: str, article_count: int, refresh_timestamp):
    cycle_counter= 0
    memory=[]
    already_exists=get_existing_articles(source, memory)
    while x!="n":
        cycle_counter+= 1
        print("Cycle "+str(cycle_counter)+" for: "+ source)
        get_feed(language, source, article_count, already_exists, memory)
        print("Done: Cycle "+str(cycle_counter)+" for: "+ source)
        time.sleep(refresh_timestamp)
#A function that starts the input termination ability and the thread for each news source, where referesh_timestamp is how many seconds do we wait before retrieving the feed.
def start(lang:str, source:list[str], article_count:int, refresh_timestamp:int):
    stop_Thread=threading.Thread(target=get_user_input,daemon=True)
    stop_Thread.start()
    print()
    for src in source:
        feed_Thread=threading.Thread(target=auto_get_feed,args=(lang,src,article_count,refresh_timestamp))
        feed_Thread.start()
    
    
# Testing:
sourceArr=["almanar","aljadeed","mtv"]
language = "arabic"
stop_event = threading.Event()
start(language,sourceArr,30,180)
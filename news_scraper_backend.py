import io
import logging
import uuid
import azure.functions as func
import requests
from bs4 import BeautifulSoup
import threading
from deep_translator import GoogleTranslator 
from datetime import datetime, timezone
import os
from typing import List
from dateutil import parser
from uuid import UUID, uuid4
from pydantic import BaseModel, EmailStr, Field
from enum import Enum
from langdetect import detect
import feedparser
import csv
from azure.storage.blob import BlobServiceClient
from schema import Article, Language, User, UserPreferences, Source


#Future dictionary to help in storing the articles of each source for future writing in a CSV file
article_Dict={}
#function to change Article to a dictionary as to print to CSV
def to_dict(article : Article):
        return {
            "id": article.id,
            "source_id": article.source_id,
            "url": article.url,
            "publish_date": article.publish_date.strftime("%Y-%m-%d %H:%M:%S") if article.publish_date else "",
            "title": article.title,
            "content": article.content,
            "language": article.language,
        }

#A thread that is used by both RSS and non-RSS sources to fill source_articles and make articles
def thread_get_content(link:str, myArticle:Article, source_articles:list[Article], src:Source):
    try:
        response = requests.get(link, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        #Use the specific locaiton we need to get the actual content of the article after acquiring the link
        article_content = soup.find(src.content_location[0], class_=src.content_location[1])
        #Sets default content to No content if no text exists in the actual article(5abar 3ajel and reminder fro nashras etc.)
        if myArticle.title and len(myArticle.title) > 3:  # Ensure it's long enough
            try:
                lang = detect(myArticle.title)
                if lang == "ar" or lang == "en":
                    myArticle.language = lang
                else:
                    raise ValueError
            except Exception as e:
                print(f"Language detection failed for title: {myArticle.title}")
                myArticle.language = "UNKNOWN"
        else:
            myArticle.language = "UNKNOWN"  # Fallback for very short titles
        myArticle.language = lang
        if not article_content:
            output_text=(f"No content to be displayed.")
            myArticle.content=(output_text)
            source_articles.append(myArticle)
            return
        text = article_content.get_text(strip=True, separator="\n")
        if text:
            if src.name=="aljadeed":
                test=text.replace("&quot;","\"")
            myArticle.content=text
            source_articles.append(myArticle)
        else:
            output_text=(f"No content to be displayed.")
            myArticle.content=output_text
            source_articles.append(myArticle)

    except Exception as e:
        print(f"error occured in threaded_get_content {src.name}")
        print(e)

#In case RSS feed exists, we call this method to populate our Array "source_articles" before making it an instance of Artic;e class
def threaded_get_feed(entry, source_articles: list[Article], src: Source, already_exists:set):
    try:
        title = entry.title
        link = entry.link
        if link in already_exists:
            return
        published = entry.published
        id = uuid.uuid4()
        myArticle = Article(id = id, source_id=src.id, content = "No content to be displayed.", title = title, url = link, publish_date = datetime.min)
        if src.name=="aljadeed":
            title=title.replace("&quot;","\"")
        myArticle.publish_date=parser.parse(published)
        thread_get_content(link,myArticle,source_articles,src)
    #Error to auto-filter articles that experienced an error...
    except Exception as e:
        print(f"error occured in threaded_get_feed() {src.name}")
    
def get_feed(src : Source, article_count: int, already_exists:set, memory: list):
    source_articles=[]
    #Handle non-RSS seperately
    if not src.has_rss:
        fetch_articles(source_articles, src, article_count, already_exists, memory)
        return
    feed = feedparser.parse(src.url)
    thread_index=0
    threads = []
    #Start a thread for each article as we populate the array, since we are accessing only a single index at max from all threads, it should be threadsafe
    for thread_index, entry in enumerate(feed.entries[:article_count]):
        thread = threading.Thread(target=threaded_get_feed, args=(entry, source_articles, src, already_exists))
        threads.append(thread)
        thread.start()
    # Wait for all threads to finish as to not preemptively use a semi-complete or empty source_articles to populate our CSV file
    for thread in threads:
        thread.join()
    
    article_Dict[src.id]=source_articles
    createCSV(src, already_exists, memory)

def get_existing_articles(src: Source, data_array: list):
    already_exists = set()
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=f"{src.name}.csv")

    try:
        # Download CSV data from Azure Blob Storage
        stream = blob_client.download_blob()
        csv_content = stream.readall().decode("utf-8")

        # Read CSV data
        reader = csv.reader(io.StringIO(csv_content), delimiter=',')
        row_index = 0

        for row in reader:
            row_index += 1
            if row_index == 1 or not row:
                continue
            
            already_exists.add(row[2])  # Add URL to existing set
            language = row[6]

            # Parse the published date correctly
            published_correct_format = datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S")

            # Create an Article object
            article = Article(
                id=row[0],
                source_id=row[1],
                url=row[2],
                publish_date=published_correct_format,
                title=row[4],
                content=row[5],
                language=Language(language),
            )

            # Append to data array
            data_array.append(article)
    
    except Exception as e:
        logging.warning(f"Could not read CSV from Azure Blob Storage for {src.name}: {e}")
    
    return already_exists


#Source being the name, and not the link, of the news organization, writes a CSV file of the total news sofar of a given news source
def createCSV(src: Source, already_exists: set, data_array: list[Article]):
    # Initialize Blob Service Client
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=f"{src.name}.csv")

    # Use in-memory string buffer instead of local file
    output = io.StringIO()
    
    fields = ["id", "source_id", "url", "publish_date", "title", "content", "language"]
    csv_writer = csv.DictWriter(output, fieldnames=fields, delimiter=',')
    
    csv_writer.writeheader()
    
    # Add new articles to the array
    for article in article_Dict[src.id]:
        if article and article.url != "":
            data_array.append(article)
            already_exists.add(article.url)
    
    # Sort articles by publish date (newest first)
    sorted_data = sorted(
        data_array,
        key=lambda x: x.publish_date.replace(tzinfo=None) if x.publish_date else datetime.min,
        reverse=True
    )

    # Write to CSV buffer
    for article in sorted_data:
        csv_writer.writerow(to_dict(article))
    
    # Upload CSV data to Azure Blob Storage
    blob_client.upload_blob(output.getvalue(), overwrite=True)
    output.close()


# Function to fetch and process the data
def fetch_articles(source_articles:list[Article], src:Source, article_count:int, already_exists:set,memory:list):
    try:
        # Send a GET request to the API
        response = requests.get(src.url)
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
            id = uuid.uuid4()
            myArticle = Article(id = id, url = article["websiteUrl"],source_id= src.id, content="No content to be displayed.", title = article["name"], publish_date=(parser.parse(article["date"])))
            thread = threading.Thread(target=thread_get_content, args=(article["websiteUrl"], myArticle, source_articles, src))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        article_Dict[src.id]=source_articles
        createCSV(src,already_exists,memory)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")


#A method that will help in creating a seperate thread fro each news source
def auto_get_feed(src : Source, article_count: int, refresh_timestamp):
    memory=[]
    already_exists=get_existing_articles(src, memory)
    get_feed(src, article_count, already_exists, memory)

#A function that starts the input termination ability and the thread for each news source, where referesh_timestamp is how many seconds do we wait before retrieving the feed.
def start(user:User, article_count:int, refresh_timestamp:int, sources : dict):
    for srcid in user.preferences.source_ids:
        source = sources.get(srcid)
        feed_Thread=threading.Thread(target=auto_get_feed,args=(source,article_count,refresh_timestamp))
        feed_Thread.start()

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
if not AZURE_STORAGE_CONNECTION_STRING:
    raise ValueError("Azure Storage connection string is missing!")
CONTAINER_NAME = "csv"
app = func.FunctionApp()

@app.timer_trigger(schedule="0 */3 * * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False) 
def timer_trigger(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Python timer trigger function executed.')
    # # Testing:
    # sourceArr = {}
    # #UUID may be random and may be hard coded as here
    # sourceArr[uuid.UUID(int=0)] = Source(id = uuid.UUID(int=0), name = "almanar", url = "https://almanar.com.lb/rss", content_location=("div","article-content"),has_rss=True)
    # sourceArr[uuid.UUID(int=1)] = Source(id = uuid.UUID(int=1),name = "aljadeed", url = "https://www.aljadeed.tv/Rss/latest-news", content_location=("div","LongDesc text-title-9"),has_rss=True)
    # sourceArr[uuid.UUID(int=2)] = Source(id = uuid.UUID(int=2),name = "mtv", url = "https://vodapi.mtv.com.lb/api/Service/GetArticlesByNewsSectionID?id=1&start=0&end=20&keywordId=-1&onlyWithSource=false&type=&authorId=-1&platform=&isLatin=", content_location=("p","_pragraphs"),has_rss=False)
    # preference = UserPreferences(source_ids = [uuid.UUID(int =0),uuid.UUID(int =1),uuid.UUID(int =2)], language = Language.ARABIC)

    # user = User(id = uuid.uuid4(),email = "email@123.com", preferences=preference)
    # start(user,15,180, sourceArr)
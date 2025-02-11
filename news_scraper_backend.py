#The code runs as expected however, some aspects are currently hardcoded(as shown by later comments) due to the fact that we are only dealing 
#with 3 sources. Time format, and how to get certain data from non-RSS, are currently hard coded, however they can be easily fixed using dictionaries
#as we have done before. In addition, optimization of threading and adding a self deleting feature so that any article older than a week/whatever time unit
#we may choose may be automatically deleted from the CSV to conserve space.
import os
import requests
from bs4 import BeautifulSoup
import threading
import feedparser
import csv
from deep_translator import GoogleTranslator
from datetime import datetime
import os
import time
from dateutil import parser
import uuid
from langdetect import detect
#Classes 
from schema import Article, Source, User, Language, UserPreferences


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
#Translates the given text into the target language using deep-translator
def translate_text(text: str, target_language: str) -> str:
    if target_language == "unknown":
        return text
    n=len(text)
    if n>5000:
        text_arr=text.split("\n")
        text=""
        for string in text_arr:
            text+= translate_text(string,target_language)+"\n"
    return GoogleTranslator(source='auto', target=target_language).translate(text)

#A thread that is used by both RSS and non-RSS sources to fill source_articles and make articles
def thread_get_content(link:str, Article2:dict, source_articles:list[Article], src:Source):
    try:
        response = requests.get(link, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        #Use the specific locaiton we need to get the actual content of the article after acquiring the link
        article_content = soup.find(src.content_location[0], class_=src.content_location[1])
        #Sets default content to No content if no text exists in the actual article(5abar 3ajel and reminder fro nashras etc.)
        id = uuid.uuid4()
        if not article_content:
            lang = detect(Article2["title"])
            output_text=(f"No content to be displayed.")
            Article2['content']=(output_text)
            #Article2['summary']=translate_text(f"Unavailable",lang)
            article = Article(id = id, source_id= src.id, url = Article2["link"], publish_date=Article2["published"], title = Article2["title"], content = Article2["content"], language=lang)
            source_articles.append(article)
            return
        text = article_content.get_text(strip=True, separator="\n")
        if text:
            lang = detect(Article2["title"])
            Article2['content']=(text)
            if src.name=="aljadeed":
                Article2['content']=Article2["content"].replace("&quot;","\"")
            article = Article(id = id, source_id= src.id, url = Article2["link"], publish_date=Article2["published"], title = Article2["title"], content = Article2["content"], language=lang)
            source_articles.append(article)
        else:
            lang = detect(Article2["title"])
            output_text=(f"No content to be displayed.")
            Article2['content']=(output_text)
            article = Article(id = id, source_id= src.id, url = Article2["link"], publish_date=Article2["published"], title = Article2["title"], content = Article2["content"], language=lang)
            source_articles.append(article)

    except Exception as e:
        #Set link and other values as N/A where they will be filtered out later on, as in not displayed in the final result
        #In case of error, the future calls get the missed news.
        output_text=(f"No content to be displayed.")
        lang = Language.UNKNOWN
        Article2['content']=(output_text)
        article = Article(id = id, source_id= src.id, url = Article2["link"], publish_date=Article2["published"], title = Article2["title"], content = Article2["content"], language=lang)
        source_articles.append(article)

#In case RSS feed exists, we call this method to populate our Array "source_articles" before making it an instance of Artic;e class
def threaded_get_feed(entry, source_articles: list[Article], src: Source, already_exists:set):
    try:
        title = entry.title
        link = entry.link
        if link in already_exists:
            return
        published = entry.published
        Article={}
        Article['title']=title
        if src.name=="aljadeed":
            Article['title']=Article['title'].replace("&quot;","\"")
        Article['link']=link
        Article['published']=parser.parse(published)
        thread_get_content(link,Article,source_articles,src)
    #Error to auto-filter articles that experienced an error...
    except Exception as e:
        print("error occured in threaded_get_feed(): "+str(e))
    
def get_feed(src : Source, article_count: int, already_exists:set, memory: list):
    source_articles=[]
    #Handle non-RSS seperately
    if not src.has_rss:
        fetch_articles(src.url, source_articles, src, article_count, already_exists, memory)
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

def get_existing_articles(src:Source, data_array:list):
    already_exists=set()
    #Check if file initially exists
    name = src.name+".csv"
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
            already_exists.add(row[2])
            language=row[6]
            # Create a dictionary for each row
            publishedCorrectFormat = datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S")
            article = Article(id = row[0], source_id=row[1],url = row[2], publish_date=publishedCorrectFormat,title = row[4],content = row[5], language=Language(language))
            #data_array is our total articles, the array we will use to write to the CSV file the total articles.
            data_array.append(article)
    return already_exists


#Source being the name, and not the link, of the news organization, writes a CSV file of the total news sofar of a given news source
def createCSV(src : Source,already_exists:set, data_array:list[Article]):
    #Write to CSV file, the new and the old data
    name = src.name+".csv"
    with open(name,'w', encoding='utf-8') as f:
        fields=["id","source_id",'url','publish_date','title','content','language']
        csv_writer=csv.DictWriter(f,fieldnames=fields,delimiter=',')
        csv_writer.writeheader()
        #Add the articles found for a given source into the total data_array
        for article in article_Dict[src.id]:
            if article and article.url != "":
                data_array.append(article)
                already_exists.add(article.url)
        #sort the array
        sorted_data = sorted(
        data_array,
        key=lambda x: x.publish_date.replace(tzinfo=None) if x.publish_date else datetime.min,
        reverse=True  # Sort in descending order
        )
    #Write the data to the CSV file.
        for article in sorted_data:
            csv_writer.writerow(to_dict(article))


# Function to fetch and process the data
def fetch_articles(url:str, source_articles:list[Article], src:Source, article_count:int, already_exists:set,memory:list):
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
            article2 = {"link" : article["websiteUrl"], "published" : parser.parse(article["date"]), "title" : article["name"]}
            thread = threading.Thread(target=thread_get_content, args=(article["websiteUrl"], article2, source_articles, src))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        article_Dict[src.id]=source_articles
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
def auto_get_feed(src : Source, article_count: int, refresh_timestamp):
    cycle_counter= 0
    memory=[]
    already_exists=get_existing_articles(src, memory)
    while x!="n":
        cycle_counter+= 1
        print("Cycle "+str(cycle_counter)+" for: "+ src.name)
        get_feed(src, article_count, already_exists, memory)
        print("Done: Cycle "+str(cycle_counter)+" for: "+ src.name)
        time.sleep(refresh_timestamp)
        
#A function that starts the input termination ability and the thread for each news source, where referesh_timestamp is how many seconds do we wait before retrieving the feed.
def start(user:User, article_count:int, refresh_timestamp:int, sources : dict):
    stop_Thread=threading.Thread(target=get_user_input,daemon=True)
    stop_Thread.start()
    print()
    for srcid in user.preferences.source_ids:
        source = sources.get(srcid)
        feed_Thread=threading.Thread(target=auto_get_feed,args=(source,article_count,refresh_timestamp))
        feed_Thread.start()
    
    
# Testing:
sourceArr = {}
almanar=Source(id=uuid.UUID(int=0),
                name="almanar",
                url="https://almanar.com.lb/rss",
                content_location=("div","article-content"),
                has_rss=True
                )
aljadeed=Source(id=uuid.UUID(int=1),
                name="aljadeed",
                url="https://www.aljadeed.tv/Rss/latest-news",
                content_location=("div","LongDesc text-title-9"),
                has_rss=True
                )
mtv= Source (id=uuid.UUID(int=2),
            name="mtv",
            url="https://vodapi.mtv.com.lb/api/Service/GetArticlesByNewsSectionID?id=1&start=0&end=20&keywordId=-1&onlyWithSource=false&type=&authorId=-1&platform=&isLatin=",
            content_location=("p","_pragraphs"),
            has_rss=False
            )
#UUID may be random and may be hard coded as here
sourceArr[uuid.UUID(int=0)] = almanar
sourceArr[uuid.UUID(int=1)] = aljadeed
sourceArr[uuid.UUID(int=2)] = mtv
preference = UserPreferences(source_ids = [uuid.UUID(int =0),uuid.UUID(int =1),uuid.UUID(int =2)], language = Language.ARABIC)
user = User(id = uuid.uuid4(),email = "email@123.com", preferences=preference)
stop_event = threading.Event()
start(user,10,180, sourceArr)
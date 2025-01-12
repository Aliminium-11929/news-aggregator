import os
import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, Text, Scrollbar, RIGHT, Y, END
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re
import threading
import feedparser
import arabic_reshaper
from bidi.algorithm import get_display
import textwrap


load_dotenv()
google_gemini_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
if not google_gemini_api_key:
    raise ValueError("Google Gemini API key not set. Check your .env file.")
feed_url = os.getenv("FEED_URL")
feed = feedparser.parse(feed_url)

Arr=["","","","",""]

# Process Arabic text function
def process_arabic_text(text, width=70):
    """
    Reshapes, displays, and aligns Arabic text to the right while preserving line order.
    Handles text wrapping and ensures proper rendering of Arabic numbers.
    """

    # Replace Arabic-indic numbers with standard Arabic numbers
    arabic_indic_to_arabic = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    text = text.translate(arabic_indic_to_arabic)

    # Wrap text to the specified width
    wrapped_lines = textwrap.fill(text, width).split("\n")
    # Process each line for Arabic reshaping and BiDi handling
    processed_lines = [get_display(arabic_reshaper.reshape(line)) for line in wrapped_lines]
    # Right-align each line to the specified width
    right_aligned_lines = [line.rjust(width) for line in processed_lines]
    return "\n".join(right_aligned_lines)

def threaded_get_feed(entry,i):
    try:
        title = get_display(arabic_reshaper.reshape(entry.title))
        link = entry.link
        published = entry.published

        response = requests.get(link, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        article_content = soup.find("div", class_="article-content")

        if not article_content:
            output_text=(f"Title: {title}\nLink: {link}\nPublished: {published}\n{'-' * 80}\n")
            Arr[i]=output_text

        text = article_content.get_text(strip=True, separator="\n")
        if text:
            reshaped_text = process_arabic_text(text, width=70)
            content = google_gemini_query(reshaped_text)
            if content:
                reshaped_content = process_arabic_text(content, width=70)
                output_text=(f"Title: {title}\nLink: {link}\nPublished: {published}\n")
                output_text+=(f"Summary:\n{reshaped_content}\n{'-' * 80}\n")
                Arr[i]=output_text
        else:
            output_text=(f"Title: {title}\nLink: {link}\nPublished: {published}\n{'-' * 80}\n")
            Arr[i]=output_text
    except Exception as e:
        output_text=(f"An error occurred: {e}\n{'-' * 80}\n")
        Arr[i]=output_text

# Google Gemini query function
def google_gemini_query(prompt):
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
        messagebox.showerror("Error", f"An error occurred: {e}")
        return None

def get_feed():
    i=0
    threads = []
    for i, entry in enumerate(feed.entries[:5]):
        thread = threading.Thread(target=threaded_get_feed, args=(entry, i))
        threads.append(thread)
        thread.start()
    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    return Arr
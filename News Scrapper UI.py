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

# Load environment variables
load_dotenv()
google_gemini_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
if not google_gemini_api_key:
    raise ValueError("Google Gemini API key not set. Check your .env file.")
feed_url = os.getenv("FEED_URL")
feed = feedparser.parse(feed_url)

# Process Arabic text function
def process_arabic_text(text, width=70):
    """
    Reshapes, displays, and aligns Arabic text to the right while preserving line order.
    Handles text wrapping and ensures proper rendering of Arabic numbers.
    """
    import textwrap

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


# Function to fetch and display feed
def get_feed_ui():
    output_text.delete("1.0", END)  # Clear previous output
    for entry in feed.entries[:5]:
        try:
            title = get_display(arabic_reshaper.reshape(entry.title))
            link = entry.link
            published = entry.published

            response = requests.get(link, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            article_content = soup.find("div", class_="article-content")

            if not article_content:
                output_text.insert(END, f"Title: {title}\nNo article content found.\n{'-' * 80}\n")
                continue

            text = article_content.get_text(strip=True, separator="\n")
            if text:
                reshaped_text = process_arabic_text(text, width=70)
                content = google_gemini_query(reshaped_text)
                if content:
                    reshaped_content = process_arabic_text(content, width=70)
                    output_text.insert(END, f"Title: {title}\nLink: {link}\nPublished: {published}\n")
                    output_text.insert(END, f"Summary:\n{reshaped_content}\n{'-' * 80}\n")
            else:
                output_text.insert(END, f"Title: {title}\nNo text content in the article.\n{'-' * 80}\n")
        except Exception as e:
            output_text.insert(END, f"An error occurred: {e}\n{'-' * 80}\n")

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

# UI setup
app = ttk.Window(themename="darkly")
app.title("News Scrapper")
app.geometry("1000x720")

# Add UI elements
frame = ttk.Frame(app)
frame.pack(fill="both", expand=True, padx=10, pady=10)

fetch_button = ttk.Button(frame, text="Fetch Feed", command=lambda: threading.Thread(target=get_feed_ui).start())
fetch_button.pack(pady=10)

output_frame = ttk.Frame(frame)
output_frame.pack(fill="both", expand=True)

output_text = Text(output_frame, wrap="word", font=("Calibri", 16), relief="flat", spacing3=10)
output_text.pack(side="left", fill="both", expand=True)

scrollbar = Scrollbar(output_frame, orient="vertical", command=output_text.yview)
scrollbar.pack(side=RIGHT, fill=Y)

output_text.config(yscrollcommand=scrollbar.set)

# Start the app
app.mainloop()

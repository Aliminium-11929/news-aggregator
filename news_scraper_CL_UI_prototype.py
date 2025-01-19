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
import News_Scrapper_Backend as backend

def get_feed_ui():
    output_text.delete("1.0", END)
    Arr=backend.get_feed()
    for s in Arr:
        output_text.insert(END, s)
    
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

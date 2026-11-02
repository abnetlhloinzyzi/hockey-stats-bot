import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from playwright.sync_api import sync_playwright
from google import genai
from google.genai.errors import APIError

# Setup Gemini API using the new client structure
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Web pages to scrape
URLS = {
    "skaters": "https://foundryadulthockey.com/player-stats/?league=48&season=177&stat_class=5",
    "goalies": "https://foundryadulthockey.com/goalie-stats/?league=48&season=177&stat_class=5",
    "schedule": "https://foundryadulthockey.com/team-page/?team=15838&league=48&season=177&tab=schedule&stat_class=5",
    "roster": "https://foundryadulthockey.com/team-page/?team=15838&league=48&season=177&tab=roster"
}

def fetch_rendered_text():
    """Spins up headless Chrome via Playwright to let JS execute before scraping text."""
    scraped_data = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for key, url in URLS.items():
            print(f"Scraping {key} from {url}...")
            page.goto(url, wait_until="networkidle")
            text_content = page.evaluate("document.body.innerText")
            scraped_data[key] = text_content[:4000] # Cap text per page to avoid context overflow
            
        browser.close()
    return scraped_data

def generate_hockey_email(data):
    """Uses Gemini to write a funny, stat-based HTML email with strict schedule anchoring."""
    today_str = datetime.today().strftime('%A, %B %d, %Y')
    
    prompt = f"""
    You are the official, hilarious, stat-loving "Beat Writer & Locker Room Analyst" for our adult rec league hockey team, **Draft League**.
    
    CRITICAL TIME ANCHOR:
    - Today's current date is: **{today_str}**. 
    - Use this date to strictly differentiate between past games (The Look-Back) and the next upcoming game (The Pre-Game Preview). Do not confuse past game results with upcoming fixtures.
    
    Here is the scraped stats and schedule data from our league website:
    --- SKATER STATS ---
    {data['skaters']}
    
    --- GOALIE STATS ---
    {data['goalies']}
    
    --- TEAM SCHEDULE & RECENT RESULTS ---
    {data['schedule']}
    
    --- TEAM ROSTER ---
    {data['roster']}
    
    TASK:
    Generate a full HTML email update (DO NOT use markdown tags like ```html - return ONLY pure valid inline-styled HTML code).
    
    HTML STYLING REQUIREMENTS:
    - Hockey-themed layout: Dark navy (#0a192f) or rink ice header, crisp white email body, dark red/blue accents (#d9534f / #0275d8).
    - Modern email formatting: Container width max 650px, styled tables for stats, bold headers, and clean callout boxes.
    
    EMAIL CONTENT STRUCTURE:
    1. **Catchy Email Subject Line** (at the very top in a designated <h2> or banner).
    2. **Part 1: The Look-Back (The Most Recent Past Game)**
       - Identify the most recent game that occurred *before* {today_str}.
       - Headline roast/praise.
       - "By the Numbers": 3 key statistics from that specific game.
       - "Star of the Game" & "Unsung Hero" (highlight hilarious metrics like PIMs or long droughts).
    3. **Part 2: The Pre-Game Preview (The Next Upcoming Matchup)**
       - Identify the next game scheduled *after* {today_str} and name the actual opponent.
       - Opponent overview & "Tale of the Tape" stat comparison.
       - Key matchup to watch.
       - Goalie duel prediction.
       - A hilarious, hyper-specific score and game event prediction.
    """
    
    # Updated to latest stable model options with fallback
    models_to_try = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
    
    response = None
    for model_name in models_to_try:
        try:
            print(f"Attempting generation with model: {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response and response.text:
                break
        except APIError as e:
            print(f"Model {model_name} failed with error: {e}. Trying next fallback...")
            continue
            
    if not response or not response.text:
        raise Exception("All model fallback options failed to generate content.")
        
    return response.text.replace("```html", "").replace("```", "").strip()

def send_email(html_body):
    """Sends the HTML email via Gmail SMTP."""
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    recipients = os.environ.get("RECIPIENT_EMAILS").split(",")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🏒 Draft League Weekly Breakdown & Pre-Game Report"
    msg["From"] = f"Draft League Beat Writer <{sender_email}>"
    msg["To"] = ", ".join(recipients)

    html_part = MIMEText(html_body, "html")
    msg.attach(html_part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipients, msg.as_string())
        
    print("Email successfully sent!")

if __name__ == "__main__":
    print("Starting Hockey Bot...")
    raw_data = fetch_rendered_text()
    email_html = generate_hockey_email(raw_data)
    send_email(email_html)
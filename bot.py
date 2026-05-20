import os, json, time, logging, hashlib, requests, asyncio, schedule
from datetime import datetime, timezone
from telegram import Bot
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value

TELEGRAM_TOKEN   = require_env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = require_env("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_jobs.json"

KEYWORDS = [
    "node.js","nodejs","mern","fastapi","langchain","genai","gen ai",
    "backend intern","python intern","react developer intern",
    "full stack intern","devops intern","ml intern","openai","llm developer",
    "ai developer","backend developer intern","javascript intern",
    "express.js","flask intern","django intern","next.js intern",
    "react native","typescript intern","rest api","mongodb",
]
BLOCKLIST = [
    "5+ years","7+ years","8+ years","10+ years",
    "senior engineer","lead engineer","principal","architect",
    "engineering manager","vp of engineering","staff engineer",
]

def load_seen():
    try:
        with open(SEEN_FILE) as f: return set(json.load(f))
    except Exception: return set()

def save_seen(seen):
    with open(SEEN_FILE,"w") as f: json.dump(list(seen)[-3000:], f)

def jid(url): return hashlib.md5(url.encode()).hexdigest()

def is_relevant(job):
    t = job["text"]
    return any(k in t for k in KEYWORDS) and not any(b in t for b in BLOCKLIST)

# ── Sources ──────────────────────────────────────────────────────
def fetch_remotive():
    jobs = []
    try:
        data = requests.get("https://remotive.com/api/remote-jobs",
            params={"category":"software-dev","limit":40}, timeout=15).json()
        for j in data.get("jobs",[]):
            text = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))}".lower()
            url  = j.get("url","")
            jobs.append({"id":jid(url),"title":j.get("title",""),"company":j.get("company_name",""),
                "url":url,"location":"Remote","source":"Remotive 🌐","easy":True,
                "text":text,"posted":j.get("publication_date","")[:10]})
    except Exception as e: log.warning(f"Remotive: {e}")
    return jobs

def fetch_arbeitnow():
    jobs = []
    try:
        data = requests.get("https://www.arbeitnow.com/api/job-board-api",
            params={"remote":"true"}, timeout=15).json()
        for j in data.get("data",[]):
            text = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))}".lower()
            url  = f"https://www.arbeitnow.com/jobs/{j.get('slug','')}"
            jobs.append({"id":jid(url),"title":j.get("title",""),"company":j.get("company_name",""),
                "url":url,"location":"Remote" if j.get("remote") else j.get("location",""),
                "source":"Arbeitnow 🌍","easy":True,"text":text,
                "posted":str(j.get("created_at",""))[:10]})
    except Exception as e: log.warning(f"Arbeitnow: {e}")
    return jobs

def fetch_hn():
    jobs = []
    try:
        user  = requests.get("https://hacker-news.firebaseio.com/v0/user/whoishiring.json", timeout=10).json()
        sid   = (user.get("submitted") or [None])[0]
        if not sid: return jobs
        story = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10).json()
        if "who is hiring" not in story.get("title","").lower(): return jobs
        for kid_id in (story.get("kids") or [])[:60]:
            try:
                kid  = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json", timeout=5).json()
                text = kid.get("text","").lower()
                url  = f"https://news.ycombinator.com/item?id={kid_id}"
                title = kid.get("text","")[:100].split("<")[0].strip() or "HN Job Post"
                jobs.append({"id":jid(url),"title":title,"company":"HN Who's Hiring",
                    "url":url,"location":"Remote / Various","source":"HackerNews 🟠",
                    "easy":False,"text":text,"posted":datetime.now(timezone.utc).strftime("%Y-%m-%d")})
            except Exception: continue
    except Exception as e: log.warning(f"HN: {e}")
    return jobs

def fetch_wellfound():
    """Wellfound public startup jobs RSS"""
    jobs = []
    try:
        import xml.etree.ElementTree as ET
        r = requests.get("https://wellfound.com/jobs.rss?role=engineer&remote=true",
            timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        root = ET.fromstring(r.content)
        for item in root.iter("item"):
            title   = item.findtext("title","")
            url     = item.findtext("link","")
            desc    = item.findtext("description","")
            company = item.findtext("{http://purl.org/dc/elements/1.1/}creator","")
            text    = f"{title} {desc}".lower()
            jobs.append({"id":jid(url),"title":title,"company":company,
                "url":url,"location":"Remote","source":"Wellfound 🚀",
                "easy":True,"text":text,"posted":datetime.now().strftime("%Y-%m-%d")})
    except Exception as e: log.warning(f"Wellfound: {e}")
    return jobs

# ── Telegram ─────────────────────────────────────────────────────
async def send_alert(new_jobs):
    bot  = Bot(token=TELEGRAM_TOKEN)
    easy = [j for j in new_jobs if j["easy"]]
    norm = [j for j in new_jobs if not j["easy"]]

    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=(f"🔥 *{len(new_jobs)} NEW JOB{'S' if len(new_jobs)>1 else ''} DETECTED*\n"
              f"_{len(easy)} Easy Apply · {len(norm)} Normal_\n"
              f"🕐 {datetime.now().strftime('%d %b %Y, %I:%M %p')} IST\n"),
        parse_mode=ParseMode.MARKDOWN
    )
    for j in sorted(new_jobs, key=lambda x: x["easy"], reverse=True)[:8]:
        badge = "⚡ *EASY APPLY*" if j["easy"] else "📋 *Apply Now*"
        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=(f"{badge}\n\n"
                      f"🎯 *{j['title']}*\n"
                      f"🏢 {j['company'] or 'Unknown'}\n"
                      f"📍 {j['location']}\n"
                      f"📅 Posted: {j['posted'] or 'Today'}\n"
                      f"🌐 {j['source']}\n\n"
                      f"🔗 [Apply Here]({j['url']})"),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )
            await asyncio.sleep(0.4)
        except Exception as e: log.warning(f"Send failed: {e}")

async def send_heartbeat():
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=("🚀 *JobBot is LIVE, Soumya\\!*\n\n"
              "I'll alert you within *5 minutes* of any new posting for:\n"
              "• Node\\.js / MERN / Backend Intern\n"
              "• GenAI / LangChain / FastAPI\n"
              "• Python / ML / DevOps Intern\n"
              "• React / Full Stack Intern\n\n"
              "📡 *Sources:* Remotive · Arbeitnow · HackerNews · Wellfound\n"
              "🕐 *Polls every:* 5 minutes, 24/7\n"
              "🧠 *Built by:* Claude for Soumya Ganguly"),
        parse_mode=ParseMode.MARKDOWN_V2
    )

# ── Main loop ─────────────────────────────────────────────────────
async def check_jobs():
    log.info("Checking for new jobs...")
    seen     = load_seen()
    all_jobs = fetch_remotive() + fetch_arbeitnow() + fetch_hn() + fetch_wellfound()
    log.info(f"Fetched {len(all_jobs)} total from all sources")
    new_jobs = []
    for job in all_jobs:
        if job["id"] not in seen and is_relevant(job):
            new_jobs.append(job)
            seen.add(job["id"])
    save_seen(seen)
    if new_jobs:
        log.info(f"✅ {len(new_jobs)} new relevant jobs — alerting Soumya")
        await send_alert(new_jobs)
    else:
        log.info("No new jobs this run")

def run_check():
    asyncio.run(check_jobs())

if __name__ == "__main__":
    log.info("🚀 Soumya JobBot starting...")
    asyncio.run(send_heartbeat())
    run_check()
    schedule.every(5).minutes.do(run_check)
    log.info("✅ Scheduler running — checking every 5 minutes")
    while True:
        schedule.run_pending()
        time.sleep(30)

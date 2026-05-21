import os, json, logging, hashlib, requests, asyncio, html, re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from telegram import Bot
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value

TELEGRAM_TOKEN = require_env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = require_env("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_jobs.json"
IST = ZoneInfo("Asia/Kolkata")

# ── Expanded keywords — SDE + Software Eng + Fresher + Remote + all roles ──
KEYWORDS = [
    # Core roles
    "software engineer intern","software developer intern","sde intern",
    "software engineering intern","junior software engineer","junior developer",
    "fresher developer","fresher engineer","entry level developer",
    "entry level engineer","entry level software","graduate developer",
    "graduate engineer","associate software engineer","associate developer",
    # Stack specific
    "node.js","nodejs","mern","fastapi","langchain","genai","gen ai",
    "backend intern","python intern","react developer intern",
    "full stack intern","devops intern","ml intern","openai","llm developer",
    "ai developer","backend developer intern","javascript intern",
    "react intern","frontend intern","web developer intern",
    "django intern","flask intern","express.js","next.js intern",
    "typescript intern","rest api intern","mongodb developer",
    "java intern","spring boot intern","kotlin intern",
    # Remote + fresher signals
    "remote intern","remote fresher","work from home intern",
    "0 years experience","0-1 years","0 to 1 year","no experience required",
    "freshers welcome","open to freshers","fresh graduate",
    # CS roles
    "software trainee","programmer analyst","technology analyst trainee",
    "systems engineer trainee","associate engineer","junior backend",
    "junior frontend","junior fullstack","junior full stack",
    # DevOps/Cloud
    "cloud intern","aws intern","devops intern","sre intern",
    "kubernetes intern","docker intern","ci cd intern",
    # Data/ML
    "data science intern","machine learning intern","data analyst intern",
    "ai intern","deep learning intern","nlp intern","computer vision intern",
]

BLOCKLIST = [
    "5+ years","6+ years","7+ years","8+ years","10+ years",
    "senior engineer","lead engineer","principal engineer",
    "engineering manager","vp engineering","director of engineering",
    "staff engineer","4+ years","3+ years experience required",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}

def load_seen():
    try:
        with open(SEEN_FILE) as f: return set(json.load(f))
    except Exception: return set()

def save_seen(seen):
    with open(SEEN_FILE,"w") as f: json.dump(sorted(seen)[-5000:], f, indent=2)

def jid(url): return hashlib.md5(url.encode()).hexdigest()

def is_relevant(job):
    t = job["text"]
    return any(k in t for k in KEYWORDS) and not any(b in t for b in BLOCKLIST)

def make_job(id_, title, company, url, location, source, easy, text, posted=""):
    return {"id":id_,"title":title,"company":company,"url":url,
            "location":location,"source":source,"easy":easy,
            "text":text,"posted":posted or datetime.now().strftime("%Y-%m-%d")}

def clean_html(value):
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

# ── Source 1: Remotive ────────────────────────────────────────────
def fetch_remotive():
    jobs = []
    try:
        data = requests.get("https://remotive.com/api/remote-jobs",
            params={"limit":50}, timeout=15, headers=HEADERS).json()
        for j in data.get("jobs",[]):
            text = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))}".lower()
            url  = j.get("url","")
            jobs.append(make_job(jid(url), j.get("title",""), j.get("company_name",""),
                url, "🌐 Remote", "Remotive", True, text, j.get("publication_date","")[:10]))
        log.info(f"Remotive: {len(jobs)} fetched")
    except Exception as e: log.warning(f"Remotive: {e}")
    return jobs

# ── Source 2: Arbeitnow ──────────────────────────────────────────
def fetch_arbeitnow():
    jobs = []
    try:
        data = requests.get("https://www.arbeitnow.com/api/job-board-api",
            params={"remote":"true"}, timeout=15, headers=HEADERS).json()
        for j in data.get("data",[]):
            text = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))}".lower()
            url  = f"https://www.arbeitnow.com/jobs/{j.get('slug','')}"
            loc  = "🌐 Remote" if j.get("remote") else f"📍 {j.get('location','')}"
            jobs.append(make_job(jid(url), j.get("title",""), j.get("company_name",""),
                url, loc, "Arbeitnow", True, text, str(j.get("created_at",""))[:10]))
        log.info(f"Arbeitnow: {len(jobs)} fetched")
    except Exception as e: log.warning(f"Arbeitnow: {e}")
    return jobs

# ── Source 3: HackerNews Who's Hiring ───────────────────────────
def fetch_hn():
    jobs = []
    try:
        user  = requests.get("https://hacker-news.firebaseio.com/v0/user/whoishiring.json", timeout=10).json()
        sid   = (user.get("submitted") or [None])[0]
        if not sid: return jobs
        story = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10).json()
        if "who is hiring" not in story.get("title","").lower(): return jobs
        for kid_id in (story.get("kids") or [])[:80]:
            try:
                kid   = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json", timeout=5).json()
                text  = kid.get("text","").lower()
                url   = f"https://news.ycombinator.com/item?id={kid_id}"
                title = kid.get("text","")[:120].split("<")[0].strip() or "HN Job"
                jobs.append(make_job(jid(url), title, "HN Who's Hiring", url,
                    "🌐 Remote / Various", "HackerNews 🟠", False, text))
            except Exception: continue
        log.info(f"HackerNews: {len(jobs)} fetched")
    except Exception as e: log.warning(f"HN: {e}")
    return jobs

# ── Source 4: Jobicy (remote-only, no signup needed) ────────────
def fetch_jobicy():
    jobs = []
    try:
        data = requests.get("https://jobicy.com/api/v2/remote-jobs",
            params={"count":30,"industry":"dev"},
            timeout=15, headers=HEADERS).json()
        for j in data.get("jobs",[]):
            text = f"{j.get('jobTitle','')} {j.get('jobDescription','')} {j.get('jobIndustry','')}".lower()
            url  = j.get("url","")
            jobs.append(make_job(jid(url), j.get("jobTitle",""), j.get("companyName",""),
                url, "🌐 Remote", "Jobicy 💼", True, text, j.get("pubDate","")[:10]))
        log.info(f"Jobicy: {len(jobs)} fetched")
    except Exception as e: log.warning(f"Jobicy: {e}")
    return jobs

# ── Source 5: RemoteOK ───────────────────────────────────────────
def fetch_remoteok():
    jobs = []
    try:
        data = requests.get("https://remoteok.com/api",
            timeout=15, headers={"User-Agent":"Mozilla/5.0"}).json()
        for j in data:
            if not isinstance(j, dict) or not j.get("position"): continue
            text = f"{j.get('position','')} {j.get('description','')} {' '.join(j.get('tags',[]))}".lower()
            url  = j.get("url","")
            jobs.append(make_job(jid(url), j.get("position",""), j.get("company",""),
                url, "🌐 Remote", "RemoteOK 🟣", True, text, j.get("date","")[:10]))
        log.info(f"RemoteOK: {len(jobs)} fetched")
    except Exception as e: log.warning(f"RemoteOK: {e}")
    return jobs

# ── Source 6: Internshala RSS (India-specific) ───────────────────
def fetch_internshala():
    jobs = []
    try:
        r = requests.get("https://internshala.com/internships/software-development-internship/",
            timeout=15, headers=HEADERS)
        for block in re.findall(r'<div class="container-fluid individual_internship.*?(?=<div class="container-fluid individual_internship|</div>\s*</div>\s*<div id=)', r.text, flags=re.S):
            href_match = re.search(r"data-href='([^']+)'", block)
            title_match = re.search(r'class="job-title-href"[^>]*>(.*?)</a>', block, flags=re.S)
            company_match = re.search(r'<p class="company-name">\s*(.*?)\s*</p>', block, flags=re.S)
            loc_match = re.search(r'<div class="row-1-item locations".*?<span>\s*(.*?)\s*</span>', block, flags=re.S)
            if not href_match or not title_match:
                continue
            title = clean_html(title_match.group(1))
            url = "https://internshala.com" + href_match.group(1)
            company = clean_html(company_match.group(1)) if company_match else "Internshala"
            loc = clean_html(loc_match.group(1)) if loc_match else "India / Remote"
            text  = f"{title} {company} {loc} software developer intern fresher".lower()
            jobs.append(make_job(jid(url), title, company,
                url, f"📍 {loc}", "Internshala 🇮🇳", True, text))
        log.info(f"Internshala: {len(jobs)} fetched")
    except Exception as e: log.warning(f"Internshala: {e}")
    return jobs

# ── Source 7: SimplifyJobs public GitHub lists ───────────────────
def fetch_simplify():
    jobs = []
    try:
        data = requests.get(
            "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
            timeout=15, headers=HEADERS).text
        previous_company = ""
        for row in re.findall(r"<tr>(.*?)</tr>", data, flags=re.S):
            cols = re.findall(r"<td>(.*?)</td>", row, flags=re.S)
            if len(cols) < 5:
                continue
            company = clean_html(cols[0]).replace("🔥", "").strip()
            if company == "↳":
                company = previous_company
            elif company:
                previous_company = company
            role = clean_html(cols[1])
            loc = clean_html(cols[2])
            urls = re.findall(r'href="([^"]+)"', cols[3])
            url = next((u for u in urls if "/p/" not in u), urls[0] if urls else "https://github.com/SimplifyJobs/Summer2026-Internships")
            text = f"{role} {company} intern software engineer developer new grad".lower()
            if company and role:
                jobs.append(make_job(jid(url+role+company), role, company,
                    url, loc or "🌐 Remote / USA", "SimplifyJobs ✨", True, text))
        log.info(f"SimplifyJobs: {len(jobs)} fetched")
    except Exception as e: log.warning(f"SimplifyJobs: {e}")
    return jobs[:30]

# ── Telegram alerts ──────────────────────────────────────────────
async def send_alert(new_jobs):
    bot  = Bot(token=TELEGRAM_TOKEN)
    easy = [j for j in new_jobs if j["easy"]]
    norm = [j for j in new_jobs if not j["easy"]]

    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=(f"🔥 *{len(new_jobs)} NEW JOB{'S' if len(new_jobs)>1 else ''} FOUND*\n"
              f"_{len(easy)} Easy Apply · {len(norm)} Normal_\n"
              f"🕐 {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')} IST"),
        parse_mode=ParseMode.MARKDOWN
    )
    for j in sorted(new_jobs, key=lambda x: x["easy"], reverse=True)[:10]:
        badge = "⚡ *EASY APPLY*" if j["easy"] else "📋 *Apply*"
        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=(f"{badge}\n\n"
                      f"🎯 *{j['title']}*\n"
                      f"🏢 {j['company'] or 'Unknown'}\n"
                      f"📍 {j['location']}\n"
                      f"📅 {j['posted'] or 'Today'}\n"
                      f"🌐 {j['source']}\n\n"
                      f"🔗 [Apply Here]({j['url']})"),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )
            await asyncio.sleep(0.5)
        except Exception as e: log.warning(f"Send failed: {e}")

async def send_update():
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=("🔄 *JobBot UPDATED to v2\\!*\n\n"
              "Now monitoring *7 sources* every 5 min:\n"
              "• Remotive\n• Arbeitnow\n• HackerNews\n"
              "• Jobicy\n• RemoteOK\n• Internshala\n• SimplifyJobs\n\n"
              "New keywords added:\n"
              "• SDE / Software Engineer Intern\n"
              "• Fresher / Entry Level / Junior\n"
              "• All remote + India roles\n"
              "• Java, Spring Boot, Cloud, Data Science"),
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def check_jobs():
    log.info("--- Checking all sources ---")
    first_run = not os.path.exists(SEEN_FILE)
    send_v2_update = os.environ.get("SEND_V2_UPDATE") == "true"
    seen = load_seen()
    all_jobs = (
        fetch_remotive()   +
        fetch_arbeitnow()  +
        fetch_hn()         +
        fetch_jobicy()     +
        fetch_remoteok()   +
        fetch_internshala()+
        fetch_simplify()
    )
    log.info(f"Total fetched: {len(all_jobs)}")
    new_jobs = []
    for job in all_jobs:
        if job["id"] not in seen and is_relevant(job):
            new_jobs.append(job)
            seen.add(job["id"])
    save_seen(seen)
    log.info(f"New matching: {len(new_jobs)}")
    if send_v2_update or first_run:
        await send_update()
    if new_jobs:
        await send_alert(new_jobs)

def run_check():
    asyncio.run(check_jobs())

if __name__ == "__main__":
    log.info("🚀 JobBot v2 one-shot check starting")
    run_check()

import os, json, logging, hashlib, requests, asyncio, html, re, base64, hmac
import xml.etree.ElementTree as ET
from collections import Counter
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

def parse_chat_ids(value):
    return list(dict.fromkeys(
        chat_id.strip()
        for chat_id in re.split(r"[,;\s]+", value or "")
        if chat_id.strip()
    ))

TELEGRAM_TOKEN = require_env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = require_env("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_IDS = parse_chat_ids(os.environ.get("TELEGRAM_CHAT_IDS")) or [TELEGRAM_CHAT_ID]
if TELEGRAM_CHAT_ID not in TELEGRAM_CHAT_IDS:
    TELEGRAM_CHAT_IDS.insert(0, TELEGRAM_CHAT_ID)
SEEN_FILE = "seen_jobs.json"
SUBSCRIBERS_FILE = "subscribers.enc.json"
IST = ZoneInfo("Asia/Kolkata")
USER_LOCATION = "Kalyani, Kolkata, West Bengal"

# ── Expanded keywords — SDE + Software Eng + Fresher + Remote + all roles ──
KEYWORDS = [
    # Core roles
    "software engineer intern","software developer intern","sde intern",
    "software engineering intern","junior software engineer","junior developer",
    "software engineer","software developer","backend engineer","backend developer",
    "frontend engineer","frontend developer","full stack developer","fullstack engineer",
    "sde 1","sde-1","developer trainee","graduate trainee","trainee engineer",
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
    "generative ai","genai engineer","prompt engineer","rag","agentic",
    "vector database","llmops","mcp server",
]

BLOCKLIST = [
    "5+ years","6+ years","7+ years","8+ years","10+ years",
    "senior engineer","lead engineer","principal engineer",
    "engineering manager","vp engineering","director of engineering",
    "staff engineer","4+ years","3+ years experience required",
]

DOMAIN_KEYWORDS = {
    "GenAI/LLM": ["genai", "gen ai", "generative ai", "llm", "openai", "rag", "langchain", "prompt engineer", "agentic", "vector database", "llmops"],
    "Backend/API": ["backend", "api", "rest", "fastapi", "flask", "django", "node", "express", "spring boot", "microservice"],
    "MERN/Full Stack": ["mern", "full stack", "fullstack", "react", "next.js", "node.js", "mongodb", "typescript", "javascript"],
    "Python/ML": ["python", "machine learning", "ml ", "data science", "deep learning", "nlp", "computer vision", "pytorch", "tensorflow"],
    "DevOps/Cloud": ["devops", "cloud", "aws", "docker", "kubernetes", "ci cd", "sre", "grafana", "datadog"],
    "Java/Spring": ["java", "spring boot", "kotlin"],
}

INDIA_TERMS = [
    "india", "indian", "kolkata", "kalyani", "west bengal", "bengaluru", "bangalore",
    "hyderabad", "pune", "mumbai", "delhi", "noida", "gurugram", "gurgaon",
    "chennai", "ahmedabad", "kochi", "remote india", "india remote",
    "maharashtra", "karnataka", "telangana", "tamil nadu", "kerala", "gujarat",
    "rajasthan", "uttar pradesh", "haryana",
]
NEARBY_TERMS = [
    "kalyani", "kolkata", "calcutta", "west bengal", "salt lake", "new town",
    "bidhannagar", "howrah", "durgapur", "barrackpore",
]
GLOBAL_REMOTE_OK_TERMS = [
    "worldwide", "global", "anywhere", "remote first", "fully remote",
    "asia", "apac", "india", "utc+5", "utc +5", "gmt+5", "gmt +5",
]
REMOTE_RESTRICTION_BLOCKS = [
    "united states only", "us only", "u.s. only", "usa only", "remote in usa",
    "remote in us", "must be based in the us", "authorized to work in the us",
    "canada only", "remote in canada", "uk only", "united kingdom only",
    "europe only", "eu only", "germany only", "australia only",
    "north america only", "latin america only", "emea only",
]
REMOTE_WORK_BLOCKS = [
    "in-person", "in person", "onsite", "on-site", "office only",
    "hybrid", "5x/week", "5 days/week",
]
STARTUP_HR_TERMS = [
    "startup", "stealth", "founding", "yc", "y combinator", "seed", "pre-seed",
    "series a", "series b", "hiring for", "for our client", "client is hiring",
    "contract", "contractual", "consultant", "staffing", "recruiter", "recruitment",
    "talent", "hr", "agency", "consultancy",
]
ENTRY_TERMS = [
    "intern", "internship", "fresher", "entry level", "junior", "graduate",
    "trainee", "0 years", "0-1", "0 to 1", "new grad", "student",
    "associate", "sde 1", "sde-1",
]
FULL_TIME_TERMS = ["full time", "full-time", "permanent", "employee"]
EXPERIENCE_BLOCK_RE = re.compile(
    r"\b(?:[3-9]|10)\s*(?:\+|–|-|to)?\s*(?:[3-9]|10)?\s*(?:years|yrs|yoe)\b|\b(?:minimum|min)\s*(?:[3-9]|10)\s*(?:years|yrs|yoe)\b",
    re.I,
)
TITLE_BLOCK_RE = re.compile(r"\b(?:senior|sr\.?|principal|staff|lead|manager|director|architect|head|vp)\b", re.I)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}
TECH_SOURCE_TERMS = [
    "software", "developer", "developers", "development", "engineer", "backend", "frontend",
    "full stack", "fullstack", "web", "programmer", "sde",
    "python", "java", "javascript", "typescript", "react", "node", "api", "devops",
    "cloud", "data", "machine learning", "ai", "ml", "llm", "genai", "fastapi",
]

def load_seen():
    try:
        with open(SEEN_FILE) as f: return set(json.load(f))
    except Exception: return set()

def save_seen(seen):
    with open(SEEN_FILE,"w") as f: json.dump(sorted(seen)[-5000:], f, indent=2)

def jid(url): return hashlib.md5(url.encode()).hexdigest()

def subscriber_key():
    return hashlib.sha256((TELEGRAM_TOKEN + ":jobbot-subscribers:v1").encode()).digest()

def xor_stream(key, nonce, data):
    stream = bytearray()
    counter = 0
    while len(stream) < len(data):
        stream.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(byte ^ mask for byte, mask in zip(data, stream))

def load_subscriber_state():
    try:
        with open(SUBSCRIBERS_FILE) as f:
            payload = json.load(f)
        key = subscriber_key()
        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ciphertext"])
        tag = base64.b64decode(payload["tag"])
        expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("subscriber state authentication failed")
        state = json.loads(xor_stream(key, nonce, ciphertext).decode())
        return {
            "chat_ids": parse_chat_ids(",".join(str(v) for v in state.get("chat_ids", []))),
            "last_update_id": int(state.get("last_update_id", 0) or 0),
        }
    except FileNotFoundError:
        return {"chat_ids": [], "last_update_id": 0}
    except Exception as e:
        log.warning(f"Subscriber state ignored: {e}")
        return {"chat_ids": [], "last_update_id": 0}

def save_subscriber_state(state):
    raw = json.dumps({
        "chat_ids": parse_chat_ids(",".join(state.get("chat_ids", []))),
        "last_update_id": int(state.get("last_update_id", 0) or 0),
    }, separators=(",", ":")).encode()
    key = subscriber_key()
    nonce = os.urandom(16)
    ciphertext = xor_stream(key, nonce, raw)
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump({
            "version": 1,
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "tag": base64.b64encode(tag).decode(),
        }, f, indent=2)

def chat_from_update(update):
    for key in ("message", "edited_message", "channel_post"):
        chat = (update.get(key) or {}).get("chat")
        if chat and chat.get("id") is not None:
            return str(chat["id"]), (update.get(key) or {}).get("text", "")
    return "", ""

def discover_subscribers():
    state = load_subscriber_state()
    known = parse_chat_ids(",".join(TELEGRAM_CHAT_IDS + state.get("chat_ids", [])))
    last_update_id = int(state.get("last_update_id", 0) or 0)
    initial_known = list(known)
    initial_last_update_id = last_update_id
    added = []

    try:
        params = {"limit": 100, "timeout": 0}
        if last_update_id:
            params["offset"] = last_update_id + 1
        data = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params=params, timeout=15
        ).json()
        if not data.get("ok"):
            raise RuntimeError(data)

        for update in data.get("result", []):
            last_update_id = max(last_update_id, int(update.get("update_id", 0) or 0))
            chat_id, text = chat_from_update(update)
            if not chat_id:
                continue
            if text and text.strip().lower().startswith("/stop"):
                known = [item for item in known if item != chat_id or item == TELEGRAM_CHAT_ID]
                continue
            if chat_id not in known:
                known.append(chat_id)
                added.append(chat_id)
    except Exception as e:
        log.warning(f"Subscriber discovery skipped: {e}")

    if known != initial_known or last_update_id != initial_last_update_id:
        save_subscriber_state({"chat_ids": known, "last_update_id": last_update_id})
    log.info(f"Active Telegram subscriber(s): {len(known)}")
    return known, added

def term_in_text(text, term):
    if re.fullmatch(r"[a-z0-9]+", term):
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
    return term in text

def contains_any(text, terms):
    return any(term_in_text(text, term) for term in terms)

def has_domain_match(text):
    return contains_any(text, KEYWORDS)

def blocked_by_seniority(job, text):
    return (
        TITLE_BLOCK_RE.search(job["title"]) is not None
        or any(b in text for b in BLOCKLIST)
        or bool(EXPERIENCE_BLOCK_RE.search(text))
    )

def classify_domains(text):
    return [name for name, terms in DOMAIN_KEYWORDS.items() if contains_any(text, terms)]

def has_entry_signal(text):
    return contains_any(text, ENTRY_TERMS)

def has_full_time_signal(text):
    return contains_any(text, FULL_TIME_TERMS)

def has_india_signal(text):
    return contains_any(text, INDIA_TERMS)

def has_nearby_signal(text):
    return contains_any(text, NEARBY_TERMS)

def has_startup_hr_signal(text):
    return contains_any(text, STARTUP_HR_TERMS)

def is_remote_text(text):
    return "remote" in text or "work from home" in text or "wfh" in text

def is_remote_workable_from_india(job, text):
    if contains_any(text, REMOTE_WORK_BLOCKS):
        return False
    restrictions = [str(v).lower() for v in job.get("location_restrictions", [])]
    if restrictions:
        joined = " ".join(restrictions)
        if contains_any(joined, REMOTE_RESTRICTION_BLOCKS):
            return False
        return contains_any(joined, GLOBAL_REMOTE_OK_TERMS + INDIA_TERMS + NEARBY_TERMS)
    if contains_any(text, REMOTE_RESTRICTION_BLOCKS):
        return False
    return is_remote_text(text) and contains_any(text, GLOBAL_REMOTE_OK_TERMS)

def enrich_job(job):
    text = f"{job['title']} {job['company']} {job['location']} {job['source']} {job['text']}".lower()
    if blocked_by_seniority(job, text) or not has_domain_match(text):
        return None

    domains = classify_domains(text)
    india = has_india_signal(text) or job["source"].startswith(("Internshala", "GradWorks", "DailyTechRoles", "Hasjob"))
    nearby = has_nearby_signal(text)
    remote_india = is_remote_workable_from_india(job, text)
    startup_signal = has_startup_hr_signal(text) or job["source"].startswith(("HackerNews", "DailyTechRoles", "Hasjob"))
    startup_hr = startup_signal and (india or remote_india)
    entry = has_entry_signal(text)
    full_time = has_full_time_signal(text) or "engineer" in job["title"].lower() or "developer" in job["title"].lower()

    if not (india or remote_india or startup_hr):
        return None
    if not (entry or full_time):
        return None

    if nearby:
        bucket = "Kolkata/West Bengal"
        fit = "Near Kalyani/Kolkata"
        priority = 5
    elif india and entry:
        bucket = "India fresher/intern"
        fit = "India fresher/intern fit"
        priority = 4
    elif remote_india:
        bucket = "Remote from India"
        fit = "Remote role workable from India"
        priority = 3
    elif startup_hr:
        bucket = "Startup/HR lead"
        fit = "Startup, HR, contract, or lesser-known hiring lead"
        priority = 2
    else:
        bucket = "Tech role"
        fit = "Relevant tech role"
        priority = 1

    job["domains"] = domains or ["Tech"]
    job["job_type"] = "Intern/Fresher" if entry else "Full-time"
    job["bucket"] = bucket
    job["fit"] = fit
    job["priority"] = priority + min(len(domains), 3)
    return job

def is_relevant(job):
    return enrich_job(job) is not None

def make_job(id_, title, company, url, location, source, easy, text, posted="", **extra):
    return {"id":id_,"title":title,"company":company,"url":url,
            "location":location,"source":source,"easy":easy,
            "text":text,"posted":posted or datetime.now().strftime("%Y-%m-%d"), **extra}

def clean_html(value):
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def html_link(url, label):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'

def parse_rss_items(xml_text):
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item"):
        yield item

def rss_item_text(item, tag):
    found = item.find(tag)
    return found.text.strip() if found is not None and found.text else ""

def first_rss_link(item):
    link = rss_item_text(item, "link")
    return link.strip()

# ── Source 1: Remotive ────────────────────────────────────────────
def fetch_remotive():
    jobs = []
    try:
        data = requests.get("https://remotive.com/api/remote-jobs",
            params={"limit":50}, timeout=15, headers=HEADERS).json()
        for j in data.get("jobs",[]):
            required_location = j.get("candidate_required_location","")
            text = (
                f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))} "
                f"{j.get('category','')} {j.get('job_type','')} {required_location}"
            ).lower()
            url  = j.get("url","")
            loc = f"🌐 Remote: {required_location}" if required_location else "🌐 Remote"
            jobs.append(make_job(jid(url), j.get("title",""), j.get("company_name",""),
                url, loc, "Remotive", True, text, j.get("publication_date","")[:10],
                location_restrictions=[required_location] if required_location else []))
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
            location = j.get("location","")
            text = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))} {location}".lower()
            url  = f"https://www.arbeitnow.com/jobs/{j.get('slug','')}"
            loc  = f"🌐 Remote: {location}" if j.get("remote") and location else "🌐 Remote" if j.get("remote") else f"📍 {location}"
            jobs.append(make_job(jid(url), j.get("title",""), j.get("company_name",""),
                url, loc, "Arbeitnow", True, text, str(j.get("created_at",""))[:10],
                location_restrictions=[location] if location else []))
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
                    "📍 See HN post", "HackerNews 🟠", False, text))
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
            geo = j.get("jobGeo","")
            industries = " ".join(j.get("jobIndustry") or [])
            job_types = " ".join(j.get("jobType") or [])
            text = (
                f"{j.get('jobTitle','')} {j.get('jobExcerpt','')} {j.get('jobDescription','')} "
                f"{industries} {job_types} {j.get('jobLevel','')} {geo}"
            ).lower()
            url  = j.get("url","")
            loc = f"🌐 Remote: {geo}" if geo else "🌐 Remote"
            jobs.append(make_job(jid(url), j.get("jobTitle",""), j.get("companyName",""),
                url, loc, "Jobicy 💼", True, text, j.get("pubDate","")[:10],
                location_restrictions=[geo] if geo else []))
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
            location = j.get("location","")
            text = f"{j.get('position','')} {j.get('description','')} {' '.join(j.get('tags',[]))} {location}".lower()
            url  = j.get("url","")
            loc = f"🌐 Remote: {location}" if location else "🌐 Remote"
            jobs.append(make_job(jid(url), j.get("position",""), j.get("company",""),
                url, loc, "RemoteOK 🟣", True, text, j.get("date","")[:10],
                location_restrictions=[location] if location else []))
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

# ── Source 8: Himalayas remote roles that allow India ────────────
def fetch_himalayas():
    jobs = []
    seen_urls = set()
    queries = [
        "software engineer",
        "backend developer",
        "python developer",
        "react developer",
        "gen ai",
        "fastapi",
    ]
    try:
        for query in queries:
            data = requests.get("https://himalayas.app/jobs/api/search",
                params={"q": query, "country": "IN", "limit": 20},
                timeout=15, headers=HEADERS).json()
            for j in data.get("jobs", []):
                url = j.get("applicationLink") or j.get("guid") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                restrictions = j.get("locationRestrictions") or []
                loc = "🌐 Remote"
                if restrictions:
                    loc = "🌐 Remote: " + ", ".join(str(v) for v in restrictions[:4])
                categories = " ".join(j.get("categories") or [])
                seniority = " ".join(j.get("seniority") or [])
                text = clean_html(
                    f"{j.get('title','')} {j.get('excerpt','')} {j.get('description','')} "
                    f"{categories} {seniority} {j.get('employmentType','')}"
                ).lower()
                posted = ""
                if j.get("pubDate"):
                    posted = datetime.fromtimestamp(int(j["pubDate"]), timezone.utc).strftime("%Y-%m-%d")
                jobs.append(make_job(jid(url), j.get("title",""), j.get("companyName",""),
                    url, loc, "Himalayas 🌎", True, text, posted,
                    location_restrictions=restrictions))
        log.info(f"Himalayas: {len(jobs)} fetched")
    except Exception as e: log.warning(f"Himalayas: {e}")
    return jobs[:60]

# ── Source 9: DailyTechRoles India fresher/intern/early jobs ─────
def fetch_dailytechroles():
    jobs = []
    seen_keys = set()
    try:
        page = requests.get("https://www.dailytechroles.com/",
            timeout=15, headers=HEADERS).text
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page)
        if not match:
            return jobs
        data = json.loads(match.group(1))
        for j in data.get("props", {}).get("pageProps", {}).get("jobs", []):
            url = j.get("applyLink") or f"https://www.dailytechroles.com/jobs/{j.get('slug','')}"
            title = j.get("title","")
            company = j.get("company","")
            loc = j.get("location","India")
            category = j.get("category","")
            experience = j.get("experience","")
            key = (title.lower(), company.lower(), loc.lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            text = f"{title} {company} {loc} {category} {experience} {j.get('description','')}".lower()
            jobs.append(make_job(jid(url), title, company, url, f"📍 {loc}",
                "DailyTechRoles 🇮🇳", True, text, category))
        log.info(f"DailyTechRoles: {len(jobs)} fetched")
    except Exception as e: log.warning(f"DailyTechRoles: {e}")
    return jobs[:60]

# ── Source 10: GradWorks India internship/fresher listings ───────
def fetch_gradworks():
    jobs = []
    try:
        page = requests.get("https://gradworks.in/",
            timeout=15, headers=HEADERS).text
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page)
        if not match:
            return jobs
        data = json.loads(match.group(1))
        for j in data.get("props", {}).get("pageProps", {}).get("jobs", []):
            title = j.get("title","")
            company = j.get("company_name","")
            loc = j.get("location","India")
            job_id = str(j.get("id",""))
            url = f"https://gradworks.in/jobs/{job_id}" if job_id else "https://gradworks.in/"
            text = (
                f"{title} {company} {loc} {j.get('job_type','')} "
                f"{j.get('experience_level','')} {' '.join(j.get('skills') or [])} "
                f"fresh graduate fresher entry level"
            ).lower()
            jobs.append(make_job(jid(url), title, company, url, f"📍 {loc}",
                "GradWorks 🇮🇳", True, text, j.get("posted_at") or j.get("experience_level") or ""))
        log.info(f"GradWorks: {len(jobs)} fetched")
    except Exception as e: log.warning(f"GradWorks: {e}")
    return jobs[:60]

# ── Source 11: Hasjob India startup jobs ─────────────────────────
def fetch_hasjob():
    jobs = []
    seen_urls = set()

    def add_hasjob_job(title, company, url, loc, posted="", description=""):
        if not title or not url or url in seen_urls:
            return
        text = f"{title} {company} {loc} {description} india startup".lower()
        if not contains_any(text, TECH_SOURCE_TERMS):
            return
        seen_urls.add(url)
        jobs.append(make_job(jid(url), title, company or "Hasjob startup", url, f"📍 {loc}",
            "Hasjob 🇮🇳", True, text, posted))

    try:
        response = requests.get("https://hasjob.co/feed", timeout=15, headers=HEADERS)
        if response.status_code == 200:
            xml_text = response.text
            entries = re.findall(r"<(?:\w+:)?entry\b[^>]*>(.*?)</(?:\w+:)?entry>", xml_text, flags=re.S)
            for entry in entries:
                title_match = re.search(r"<(?:\w+:)?title\b[^>]*>(.*?)</(?:\w+:)?title>", entry, flags=re.S)
                link_match = re.search(r'<(?:\w+:)?link\b[^>]*href="([^"]+)"', entry)
                id_match = re.search(r"<(?:\w+:)?id\b[^>]*>(.*?)</(?:\w+:)?id>", entry, flags=re.S)
                loc_match = re.search(r"<(?:\w+:)?location\b[^>]*>(.*?)</(?:\w+:)?location>", entry, flags=re.S)
                content_match = re.search(r"<(?:\w+:)?content\b[^>]*>(.*?)</(?:\w+:)?content>", entry, flags=re.S)
                published_match = re.search(r"<(?:\w+:)?published\b[^>]*>(.*?)</(?:\w+:)?published>", entry, flags=re.S)
                title = clean_html(html.unescape(title_match.group(1))) if title_match else ""
                url = link_match.group(1).strip() if link_match else clean_html(id_match.group(1)) if id_match else ""
                loc = clean_html(html.unescape(loc_match.group(1))) if loc_match else "India / Remote"
                content = html.unescape(content_match.group(1)) if content_match else ""
                company_match = re.search(r"<strong>\s*<a[^>]*>(.*?)</a>", content, flags=re.S)
                company = clean_html(company_match.group(1)) if company_match else "Hasjob startup"
                posted = clean_html(published_match.group(1))[:10] if published_match else ""
                add_hasjob_job(title, company, url, loc, posted, clean_html(content))
        else:
            log.info(f"Hasjob feed HTTP {response.status_code}; using reader fallback")

        if not jobs:
            page = requests.get("https://r.jina.ai/https://hasjob.co/",
                timeout=20, headers=HEADERS).text
            for body, url in re.findall(r"^\*\s+\[(.*?)\]\((https://hasjob\.co/[^)]+)\)", page, flags=re.M):
                date_match = re.search(r"\b(\d{1,2}\s+\w+\s+’\d{2})\b", body)
                loc = "India / Remote"
                title = clean_html(body)
                posted = ""
                if date_match:
                    loc = clean_html(body[:date_match.start()]) or loc
                    posted = date_match.group(1)
                    title = clean_html(body[date_match.end():])
                company_slug = url.rstrip("/").split("/")[-2] if len(url.rstrip("/").split("/")) > 3 else ""
                company = company_slug.replace("-", " ").replace(".com", "").replace(".in", "").replace(".ai", "").title()
                add_hasjob_job(title, company, url, loc, posted, title)
        log.info(f"Hasjob: {len(jobs)} fetched")
    except Exception as e: log.warning(f"Hasjob: {e}")
    return jobs[:40]

# ── Source 12: Remote First Jobs public API ──────────────────────
def fetch_remotefirst():
    jobs = []
    seen_urls = set()
    requests_to_make = [
        {"category": "software-development", "page": 0},
        {"category": "data", "page": 0},
        {"category": "devops-and-sre", "page": 0},
        {"query": "python", "page": 0},
        {"query": "react", "page": 0},
        {"query": "gen ai", "page": 0},
        {"query": "intern", "page": 0},
    ]
    try:
        for params in requests_to_make:
            data = requests.get("https://remotefirstjobs.com/api/search-jobs",
                params=params, timeout=15, headers=HEADERS).json()
            for j in data.get("jobs", []):
                url = j.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                locs = [str(v) for v in (j.get("locations") or []) if v]
                loc = "🌐 Remote"
                if locs:
                    loc = "🌐 Remote: " + ", ".join(locs[:4])
                seniority = j.get("seniority") or ""
                text = clean_html(
                    f"{j.get('title','')} {j.get('company_name','')} {j.get('description','')} "
                    f"{j.get('category','')} {seniority} {' '.join(locs)}"
                ).lower()
                jobs.append(make_job(jid(url), j.get("title",""), j.get("company_name",""),
                    url, loc, "Remote First Jobs 🛰️", True, text, str(j.get("published_at",""))[:10],
                    location_restrictions=locs, remote_first_credit=True))
        log.info(f"RemoteFirstJobs: {len(jobs)} fetched")
    except Exception as e: log.warning(f"RemoteFirstJobs: {e}")
    return jobs[:80]

# ── Source 13: RemoteJobs.org public API ─────────────────────────
def fetch_remotejobs_org():
    jobs = []
    seen_urls = set()
    params_list = [
        {"category": "programming", "limit": 50},
        {"category": "devops", "limit": 50},
        {"category": "data-science", "limit": 50},
        {"q": "python", "limit": 50},
        {"q": "react", "limit": 50},
        {"q": "backend", "limit": 50},
        {"q": "ai", "limit": 50},
    ]
    try:
        for params in params_list:
            try:
                response = requests.get("https://remotejobs.org/api/v1/jobs",
                    params=params, timeout=15, headers=HEADERS)
                if response.status_code != 200:
                    log.warning(f"RemoteJobs.org query {params}: HTTP {response.status_code}")
                    if response.status_code == 429:
                        break
                    continue
                data = response.json()
            except Exception as e:
                log.warning(f"RemoteJobs.org query {params}: {e}")
                continue
            for j in data.get("data", []):
                url = j.get("apply_url") or j.get("url") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                company = (j.get("company") or {}).get("name", "")
                loc = j.get("location") or "Remote"
                category = (j.get("category") or {}).get("name", "")
                text = clean_html(
                    f"{j.get('title','')} {company} {j.get('description','')} "
                    f"{category} {j.get('type','')} {loc}"
                ).lower()
                jobs.append(make_job(jid(url), j.get("title",""), company,
                    url, f"🌐 {loc}", "RemoteJobs.org 🌍", True, text, str(j.get("posted_at",""))[:10],
                    location_restrictions=[loc]))
        log.info(f"RemoteJobs.org: {len(jobs)} fetched")
    except Exception as e: log.warning(f"RemoteJobs.org: {e}")
    return jobs[:80]

# ── Source 14: Working Nomads public jobs API ────────────────────
def fetch_workingnomads():
    jobs = []
    try:
        data = requests.get("https://www.workingnomads.com/api/exposed_jobs/",
            timeout=15, headers=HEADERS).json()
        for j in data:
            title = j.get("title","")
            company = j.get("company_name","")
            loc = j.get("location","Remote")
            category = j.get("category_name","")
            tags = j.get("tags","")
            description = j.get("description","")
            text = clean_html(f"{title} {company} {loc} {category} {tags} {description}").lower()
            if category.lower() != "development" and not contains_any(text, TECH_SOURCE_TERMS):
                continue
            url = j.get("url","")
            jobs.append(make_job(jid(url), title, company, url, f"🌐 Remote: {loc}",
                "Working Nomads 🧭", True, text, str(j.get("pub_date",""))[:10],
                location_restrictions=[loc]))
        log.info(f"WorkingNomads: {len(jobs)} fetched")
    except Exception as e: log.warning(f"WorkingNomads: {e}")
    return jobs[:60]

# ── Source 15: We Work Remotely programming RSS ─────────────────
def fetch_weworkremotely():
    jobs = []
    try:
        xml_text = requests.get("https://weworkremotely.com/categories/remote-programming-jobs.rss",
            timeout=15, headers=HEADERS).text
        for item in parse_rss_items(xml_text):
            raw_title = clean_html(rss_item_text(item, "title"))
            if not raw_title:
                continue
            company = "We Work Remotely"
            title = raw_title
            if ":" in raw_title:
                company, title = [part.strip() for part in raw_title.split(":", 1)]
            url = first_rss_link(item)
            description = clean_html(rss_item_text(item, "description"))
            posted = rss_item_text(item, "pubDate")[:16]
            loc_match = re.search(r"(?:Region|Location):\s*([^<\n]+)", description, flags=re.I)
            loc = clean_html(loc_match.group(1)) if loc_match else "Remote"
            text = f"{title} {company} {description} {loc} worldwide anywhere global remote".lower()
            jobs.append(make_job(jid(url), title, company, url, f"🌐 Remote: {loc}",
                "WeWorkRemotely 🧑‍💻", True, text, posted,
                location_restrictions=[loc]))
        log.info(f"WeWorkRemotely: {len(jobs)} fetched")
    except Exception as e: log.warning(f"WeWorkRemotely: {e}")
    return jobs[:50]

# ── Source 16: NoDesk remote developer listings ─────────────────
def fetch_nodesk():
    jobs = []
    seen_urls = set()
    pages = [
        "https://nodesk.co/remote-jobs/developer/",
        "https://nodesk.co/remote-jobs/software-developer/",
        "https://nodesk.co/remote-jobs/backend-developer/",
        "https://nodesk.co/remote-jobs/frontend-developer/",
    ]
    try:
        for page_url in pages:
            page = requests.get(page_url, timeout=15, headers=HEADERS).text
            for block in re.split(r'<li class="dt-s dt-ns', page)[1:]:
                title_match = re.search(r'<h2[^>]*>.*?<a[^>]+href=["\']?([^"\' >]+)["\']?[^>]*>(.*?)</a>', block, flags=re.S)
                if not title_match:
                    continue
                url = title_match.group(1)
                if url.startswith("/"):
                    url = "https://nodesk.co" + url
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                title = clean_html(title_match.group(2))
                company_match = re.search(r'<h3[^>]*class="[^"]*grey-900[^"]*lh-copy[^"]*"[^>]*>(.*?)</h3>', block, flags=re.S)
                logo_match = re.search(r'alt="([^"]+) logo"', block)
                company = clean_html(company_match.group(1)) if company_match else ""
                if not company and logo_match:
                    company = clean_html(logo_match.group(1))
                if not company:
                    company = "NoDesk company"
                remote_match = re.search(r'Remote:</h4>\s*<h5[^>]*>(.*?)</h5>', block, flags=re.S)
                loc = clean_html(remote_match.group(1)) if remote_match else "Remote"
                tags = " ".join(clean_html(tag) for tag in re.findall(r'<li class="dib.*?>(.*?)</li>', block, flags=re.S))
                text = f"{title} {company} {loc} {tags} remote worldwide anywhere full-time developer engineer".lower()
                jobs.append(make_job(jid(url), title, company, url, f"🌐 Remote: {loc}",
                    "NoDesk 🌐", True, text, "",
                    location_restrictions=[loc]))
        log.info(f"NoDesk: {len(jobs)} fetched")
    except Exception as e: log.warning(f"NoDesk: {e}")
    return jobs[:80]

# ── Source 17: Python.org official jobs RSS ─────────────────────
def fetch_python_org():
    jobs = []
    try:
        xml_text = requests.get("https://www.python.org/jobs/feed/rss/",
            timeout=15, headers=HEADERS).text
        for item in parse_rss_items(xml_text):
            raw_title = clean_html(rss_item_text(item, "title"))
            if not raw_title:
                continue
            title = raw_title
            company = "Python.org job board"
            if ", " in raw_title:
                title, company = [part.strip() for part in raw_title.rsplit(", ", 1)]
            url = first_rss_link(item)
            raw_description = rss_item_text(item, "description")
            loc = clean_html(re.split(r"<p\b", raw_description, maxsplit=1, flags=re.I)[0]) or "Remote / Global"
            description = clean_html(raw_description)
            text = f"{title} {company} {description} {loc} python backend django flask fastapi ai ml remote".lower()
            jobs.append(make_job(jid(url), title, company, url, f"🌐 {loc}",
                "Python.org 🐍", True, text, rss_item_text(item, "pubDate")[:16],
                location_restrictions=[loc]))
        log.info(f"Python.org: {len(jobs)} fetched")
    except Exception as e: log.warning(f"Python.org: {e}")
    return jobs[:50]

# ── Source 18: Physical AI Jobs RSS ─────────────────────────────
def fetch_physicalai():
    jobs = []
    try:
        xml_text = requests.get("https://www.physicalai.jobs/jobs.rss",
            timeout=15, headers=HEADERS).text
        for item in parse_rss_items(xml_text):
            title = clean_html(rss_item_text(item, "title"))
            url = first_rss_link(item)
            if not title or not url:
                continue
            path_parts = [part for part in url.split("/") if part]
            company = path_parts[2].replace("-", " ").title() if len(path_parts) > 2 else "Physical AI company"
            description = clean_html(rss_item_text(item, "description"))
            text = f"{title} {company} {description} ai machine learning ml robotics computer vision autonomy".lower()
            jobs.append(make_job(jid(url), title, company, url, "🤖 AI / Robotics",
                "Physical AI Jobs 🤖", True, text, rss_item_text(item, "pubDate")[:16]))
        log.info(f"PhysicalAI: {len(jobs)} fetched")
    except Exception as e: log.warning(f"PhysicalAI: {e}")
    return jobs[:50]

# ── Telegram alerts ──────────────────────────────────────────────
async def safe_send_message(bot, chat_id, **kwargs):
    try:
        await bot.send_message(chat_id=chat_id, **kwargs)
        return True
    except Exception as e:
        log.warning(f"Telegram send failed for one subscriber: {e}")
        return False

async def send_alert(new_jobs, chat_ids):
    bot  = Bot(token=TELEGRAM_TOKEN)
    easy = [j for j in new_jobs if j["easy"]]
    norm = [j for j in new_jobs if not j["easy"]]
    bucket_counts = Counter(j.get("bucket", "Tech role") for j in new_jobs)
    bucket_summary = " · ".join(f"{count} {bucket}" for bucket, count in bucket_counts.most_common())

    jobs_to_send = sorted(new_jobs, key=lambda x: (x.get("priority", 0), x["easy"]), reverse=True)[:12]
    any_sent = False
    log.info(f"Sending alerts to {len(chat_ids)} subscriber(s)")
    for chat_id in chat_ids:
        header_sent = await safe_send_message(
            bot,
            chat_id,
            text=(f"🔥 <b>{len(new_jobs)} NEW JOB{'S' if len(new_jobs)>1 else ''} FOUND</b>\n"
                  f"<i>{len(easy)} Easy Apply · {len(norm)} Normal</i>\n"
                  f"🧭 {html.escape(bucket_summary)}\n"
                  f"📍 Optimized for {html.escape(USER_LOCATION)}\n"
                  f"🕐 {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')} IST"),
            parse_mode=ParseMode.HTML
        )
        if not header_sent:
            continue
        any_sent = True
        for j in jobs_to_send:
            badge = "⚡ EASY APPLY" if j["easy"] else "📋 Apply"
            domains = ", ".join(j.get("domains") or ["Tech"])
            await safe_send_message(
                bot,
                chat_id,
                text=(f"{badge}\n\n"
                      f"🎯 <b>{html.escape(j['title'])}</b>\n"
                      f"🏢 {html.escape(j['company'] or 'Unknown')}\n"
                      f"📍 {html.escape(j['location'])}\n"
                      f"🧭 {html.escape(j.get('fit', 'Relevant tech role'))}\n"
                      f"🏷 {html.escape(domains)} · {html.escape(j.get('job_type','Tech'))}\n"
                      f"📅 {html.escape(j['posted'] or 'Today')}\n"
                      f"🌐 {html.escape(j['source'])}\n\n"
                      f"🔗 {html_link(j['url'], 'Apply Here')}"),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False
            )
            await asyncio.sleep(0.5)
    return any_sent

async def send_update(chat_ids):
    bot = Bot(token=TELEGRAM_TOKEN)
    any_sent = False
    for chat_id in chat_ids:
        sent = await safe_send_message(
            bot,
            chat_id,
            text=(f"🔄 <b>JobBot UPDATED to v4</b>\n\n"
                  f"Optimized for <b>{html.escape(USER_LOCATION)}</b>.\n\n"
                  "Now classifying jobs into:\n"
                  "• Kolkata / West Bengal nearby\n"
                  "• India fresher / intern\n"
                  "• Global remote workable from India\n"
                  "• Startup / HR / contract hiring leads\n\n"
                  "Newer niche sources included:\n"
                  "• Hasjob India startup jobs\n"
                  "• Remote First Jobs public API\n"
                  "• RemoteJobs.org public API\n"
                  "• Working Nomads public API\n"
                  "• We Work Remotely programming RSS\n"
                  "• NoDesk worldwide developer jobs\n"
                  "• Python.org jobs RSS\n"
                  "• Physical AI Jobs RSS\n\n"
                  "Better filtering for GenAI, Backend, MERN, Python/ML, DevOps, Java/Spring."),
            parse_mode=ParseMode.HTML
        )
        any_sent = any_sent or sent
    return any_sent

async def send_welcome(chat_ids):
    bot = Bot(token=TELEGRAM_TOKEN)
    for chat_id in chat_ids:
        await safe_send_message(
            bot,
            chat_id,
            text=("✅ <b>You are subscribed to Soumya JobBot</b>\n\n"
                  "You will receive classified job alerts when new matching roles are found.\n"
                  "Send /stop to unsubscribe."),
            parse_mode=ParseMode.HTML
        )

async def check_jobs():
    log.info("--- Checking all sources ---")
    first_run = not os.path.exists(SEEN_FILE)
    send_update_requested = (
        os.environ.get("SEND_UPDATE") == "true"
        or os.environ.get("SEND_V2_UPDATE") == "true"
    )
    chat_ids, new_subscribers = discover_subscribers()
    seen = load_seen()
    all_jobs = (
        fetch_remotive()   +
        fetch_arbeitnow()  +
        fetch_hn()         +
        fetch_jobicy()     +
        fetch_remoteok()   +
        fetch_internshala()+
        fetch_simplify()   +
        fetch_himalayas()  +
        fetch_dailytechroles() +
        fetch_gradworks()      +
        fetch_hasjob()         +
        fetch_remotefirst()    +
        fetch_remotejobs_org() +
        fetch_workingnomads()  +
        fetch_weworkremotely() +
        fetch_nodesk()         +
        fetch_python_org()     +
        fetch_physicalai()
    )
    log.info(f"Total fetched: {len(all_jobs)}")
    new_jobs = []
    for job in all_jobs:
        if job["id"] not in seen and is_relevant(job):
            new_jobs.append(job)
            seen.add(job["id"])
    log.info(f"New matching: {len(new_jobs)}")
    try:
        if new_subscribers:
            await send_welcome(new_subscribers)
        if send_update_requested or first_run:
            await send_update(chat_ids)
        if new_jobs:
            if not await send_alert(new_jobs, chat_ids):
                raise RuntimeError("No Telegram subscribers accepted job alerts")
    except Exception:
        log.exception("Telegram send failed; leaving jobs unseen for a retry")
        raise
    save_seen(seen)

def run_check():
    asyncio.run(check_jobs())

if __name__ == "__main__":
    log.info("🚀 JobBot v4 one-shot check starting")
    run_check()

import os, json, logging, hashlib, requests, asyncio, html, re, base64, hmac
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
    india = has_india_signal(text) or job["source"].startswith(("Internshala", "GradWorks", "DailyTechRoles"))
    nearby = has_nearby_signal(text)
    remote_india = is_remote_workable_from_india(job, text)
    startup_signal = has_startup_hr_signal(text) or job["source"].startswith(("HackerNews", "DailyTechRoles"))
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
            text=(f"🔄 <b>JobBot UPDATED to v3</b>\n\n"
                  f"Optimized for <b>{html.escape(USER_LOCATION)}</b>.\n\n"
                  "Now classifying jobs into:\n"
                  "• Kolkata / West Bengal nearby\n"
                  "• India fresher / intern\n"
                  "• Global remote workable from India\n"
                  "• Startup / HR / contract hiring leads\n\n"
                  "New sources added:\n"
                  "• Himalayas remote jobs API\n"
                  "• DailyTechRoles India fresher roles\n"
                  "• GradWorks India internships and entry-level jobs\n\n"
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
        fetch_dailytechroles()+
        fetch_gradworks()
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
    log.info("🚀 JobBot v3 one-shot check starting")
    run_check()

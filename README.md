# Soumya JobBot 🤖

Telegram job alert bot for Soumya in Kalyani/Kolkata, West Bengal. It checks
on the configured external schedule for SDE, software engineer, fresher,
entry-level, intern, GenAI, remote-from-India, and India startup/HR hiring leads.

## Run on GitHub Actions + Google Apps Script (free)

This bot is triggered by Google Apps Script and runs on GitHub Actions. The
recommended trigger is every 2 hours, which is 12 checks per day.

1. Add repository secrets:
   - TELEGRAM_TOKEN
   - TELEGRAM_CHAT_ID
   - TELEGRAM_CHAT_IDS (optional comma-separated list for multiple subscribers)
2. Enable Actions for the repo.
3. Use Google Apps Script to trigger `.github/workflows/jobbot.yml` with
   `workflow_dispatch`.

Alerts are grouped as Kolkata/West Bengal, India fresher/intern, remote from India,
and startup/HR leads. Later runs only alert for new matching jobs.

## Multiple Telegram Subscribers

The default `TELEGRAM_CHAT_ID` receives all alerts. To send alerts to friends too,
either ask them to send `/start` to the bot or add a GitHub secret named
`TELEGRAM_CHAT_IDS`:

```text
your_chat_id,friend_chat_id,another_friend_chat_id
```

Each friend must open the Telegram bot and press Start once before Telegram allows
the bot to send them messages.

The bot auto-detects new `/start` messages during each scheduled run and stores
subscriber state in `subscribers.enc.json`. That file is encrypted with the
Telegram token secret, so chat IDs are not committed in plain text.

## Sources monitored

- Remotive
- Arbeitnow
- HackerNews Who's Hiring
- Jobicy
- RemoteOK
- Internshala
- SimplifyJobs
- Himalayas
- DailyTechRoles
- GradWorks

## Optional Render Deploy

1. Fork or push this repo to your GitHub
2. Go to render.com → New → Background Worker
3. Connect your GitHub repo
4. Render auto-reads render.yaml — enter TELEGRAM_TOKEN and TELEGRAM_CHAT_ID when prompted
5. Done. Bot sends a confirmation to Telegram instantly.

Render Background Workers can require a paid plan. GitHub Actions is the free path for this repo.

## Configuration

Set these environment variables:

- TELEGRAM_TOKEN
- TELEGRAM_CHAT_ID
- TELEGRAM_CHAT_IDS (optional)

`render.yaml` uses `sync: false` so secret values are entered in Render instead of committed to GitHub.

## Keywords filtered
SDE intern, software engineer intern, fresher developer, entry level engineer,
junior developer, Node.js, MERN, FastAPI, LangChain, GenAI, Python, React,
Backend, DevOps, ML, Java, Spring Boot, Cloud, Data Science

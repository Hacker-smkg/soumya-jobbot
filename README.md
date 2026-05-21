# Soumya JobBot 🤖

Telegram job alert bot — pings Soumya within 5 minutes of new SDE,
software engineer, fresher, entry-level, intern, remote, and India-specific roles.

## Run on GitHub Actions (free)

This bot runs every 5 minutes with GitHub Actions and sends Telegram alerts from 7 sources.

1. Add repository secrets:
   - TELEGRAM_TOKEN
   - TELEGRAM_CHAT_ID
2. Enable Actions for the repo.
3. The workflow in `.github/workflows/jobbot.yml` runs automatically every 5 minutes.

The first run bootstraps existing jobs. Later runs only alert for new matching jobs.

## Sources monitored

- Remotive
- Arbeitnow
- HackerNews Who's Hiring
- Jobicy
- RemoteOK
- Internshala
- SimplifyJobs

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

`render.yaml` uses `sync: false` so secret values are entered in Render instead of committed to GitHub.

## Keywords filtered
SDE intern, software engineer intern, fresher developer, entry level engineer,
junior developer, Node.js, MERN, FastAPI, LangChain, GenAI, Python, React,
Backend, DevOps, ML, Java, Spring Boot, Cloud, Data Science

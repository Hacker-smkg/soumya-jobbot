# Soumya JobBot 🤖

Telegram job alert bot — pings Soumya within 5 minutes of any new
Node.js / MERN / GenAI / FastAPI / Backend intern posting.

## Run on GitHub Actions (free)

This bot runs every 5 minutes with GitHub Actions and sends Telegram alerts.

1. Add repository secrets:
   - TELEGRAM_TOKEN
   - TELEGRAM_CHAT_ID
2. Enable Actions for the repo.
3. The workflow in `.github/workflows/jobbot.yml` runs automatically every 5 minutes.

The first run bootstraps existing jobs and sends a live message. Later runs only alert for new matching jobs.

## Deploy to Render

1. Fork or push this repo to your GitHub
2. Go to render.com → New → Background Worker
3. Connect your GitHub repo
4. Render auto-reads render.yaml — enter TELEGRAM_TOKEN and TELEGRAM_CHAT_ID when prompted
5. Done. Bot sends a confirmation to Telegram instantly.

## Configuration

Set these environment variables:

- TELEGRAM_TOKEN
- TELEGRAM_CHAT_ID

`render.yaml` uses `sync: false` so secret values are entered in Render instead of committed to GitHub.

## Sources monitored
- Remotive (remote jobs)
- Arbeitnow (remote global)
- HackerNews Who's Hiring
- Wellfound (startup jobs)

## Keywords filtered
Node.js, MERN, FastAPI, LangChain, GenAI, Python intern,
React intern, Backend intern, DevOps intern, ML intern

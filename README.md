# shopping-list

A Telegram-driven shopping list with a companion web app, **learned price
predictions**, and spending **statistics**.

1. Send your shopping list to a **Telegram bot** (one item per line, or comma separated).
2. The bot **stores** it, **auto-categorizes** each item (produce, dairy, …), and
   replies with a **private web link**.
3. On the web page, **tap items** to mark them bought — they move to a "Bought"
   section. Each item shows a **predicted price** and you see a **predicted total**.
4. When everything is bought, **enter what you actually paid**. That total is saved
   for **monthly/yearly statistics** and feeds future price predictions.

Predicted prices are learned from **your own** past purchases (the average of recent
real prices for the same item). The first time you buy an item there's no personal
history, so the price falls back to a **shared global catalog** scraped daily from the
Shufersal price feed. When a typed term is generic ("פלפל"), the web list offers the
matching **variants** ("פלפל אדום", "פלפל צהוב") to pick from. See
[docs/price-fetch-cron.md](docs/price-fetch-cron.md) for the daily catalog job.

> Working on the code? See [CLAUDE.md](CLAUDE.md) for the architecture, conventions,
> and commands (also used by Claude Code).

## Architecture

| Component | Tech |
|-----------|------|
| Telegram bot | Python, [aiogram](https://docs.aiogram.dev) (long polling) |
| Web app/API | [FastAPI](https://fastapi.tiangolo.com) + Jinja2 + vanilla JS |
| Database | PostgreSQL (SQLAlchemy 2.0 + Alembic migrations) |
| Deploy | Docker Compose (`db`, `migrate`, `web`, `bot`; `price-fetch` job via cron) |

```
app/
  config.py        settings from env
  db.py            engine + sessions
  models.py        User, ShoppingList, Item, PriceHistory
  parsing.py       free text -> items (quantities, bullets, commas)
  categories.py    keyword map + categorize()
  pricing.py       normalize_name() + learned predicted_price()
  global_prices.py global catalog matching + variant suggestions
  stats.py         monthly/yearly aggregation
  services.py      shared business logic (create/toggle/complete/resolve_variant)
  bot/             aiogram handlers + entrypoint
  web/             FastAPI routes, templates, static
  jobs/            fetch_prices.py — daily global catalog refresh
mockups/           standalone clickable HTML mockups (open index.html)
migrations/        Alembic
tests/             pytest
```

## Quick start (local, Docker)

```bash
cp .env.example .env          # then edit: set BOT_TOKEN, passwords, WEB_BASE_URL
docker compose up -d --build  # starts db, runs migrations, then web + bot
```

The web app is now on `http://localhost:8000`. Message your bot on Telegram with a
list to get a link.

## Local development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# point DATABASE_URL at a local Postgres, then:
alembic upgrade head
uvicorn app.web.main:app --reload        # web
python -m app.bot.main                    # bot (in another terminal)
pytest                                     # tests
```

## Telegram bot commands

| Input | Action |
|-------|--------|
| _(any text)_ | Create a new categorized list, reply with a web link |
| `/start` | Register and show help |
| `/lists` | Recent lists with links |
| `/stats` | Link to your statistics dashboard |
| `/currency USD` | Set your currency |

Get a bot token from [@BotFather](https://t.me/BotFather) and put it in `.env`.

## Deploying to your VPS

1. Install Docker + Docker Compose on the VPS.
2. Clone this repo and create `.env` (set a strong `POSTGRES_PASSWORD`, your
   `BOT_TOKEN`, and `WEB_BASE_URL` to your public HTTPS URL).
3. `docker compose up -d --build`.
4. Put the web service behind a reverse proxy with TLS so `WEB_BASE_URL` works.
   Example nginx server block:

   ```nginx
   server {
       server_name shop.example.com;
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   Then issue a certificate with `certbot --nginx -d shop.example.com`.

Access control: list and stats pages are reached via unguessable random tokens in the
URL, so only people you share a link with (or yourself, via the bot) can open them.

## Mockups

Open `mockups/index.html` in a browser to see all screens (Telegram chat, arranged
list, all-bought/price entry, statistics). They are static — no backend needed.

## Tests

```bash
pytest
```

Covers list parsing, categorization, price learning, and the create→toggle→complete
service flow (SQLite in-memory; no Postgres required for the test suite).

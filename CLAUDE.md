# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Tests (SQLite in-memory; no Postgres needed)
pytest                              # full suite
pytest tests/test_services.py       # one file
pytest tests/test_pricing.py::test_predicted_price_uses_most_recent   # one test

# Run locally without Docker (needs a Postgres at DATABASE_URL)
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.web.main:app --reload   # web on :8000
python -m app.bot.main              # bot (separate terminal)

# Docker (full stack: db -> migrate -> web + bot)
docker compose up -d --build
docker compose logs -f bot

# Daily global-catalog refresh (not started by `up`; profiles: ["jobs"])
docker compose run --rm price-fetch          # == python -m app.jobs.fetch_prices

# Migrations (after changing app/models.py)
alembic revision -m "describe change"        # then edit; keep the 000N_ numbering
alembic upgrade head
```

There is no linter/formatter configured. Python 3.11+, 4-space indent, `from __future__ import annotations` at the top of modules.

## Architecture

Two entrypoints — the **Telegram bot** (aiogram long polling, `app/bot/`) and the
**FastAPI web app** (`app/web/`) — share one PostgreSQL database and, crucially, **one
business-logic layer in [app/services.py](app/services.py)**. The bot parses messages and
renders keyboards; the web app renders the list/stats pages and handles taps. Neither
should reimplement list/pricing logic — both call `services.py` (`create_list_from_text`,
`toggle_item`, `complete_list`, `end_list`, `add_item_from_pending`, `resolve_variant`,
`resolve_custom_variant`). Put new shared behavior there.

### Session/commit conventions differ by entrypoint
- **Bot** uses `session_scope()` ([app/db.py](app/db.py)) — a context manager that commits
  on clean exit. Handlers do not call `commit()`.
- **Web** uses the `get_session()` FastAPI dependency, which does **not** commit. Each route
  must call `session.commit()` itself before returning (see [app/web/routes.py](app/web/routes.py)).
- `SessionLocal` is configured `autoflush=False`. When a later query depends on a pending
  insert/delete (e.g. rebuilding a keyboard after deleting a row), call `session.flush()`
  explicitly. Services rely on this in several places.

### Pricing model — three layers, history is the source of truth
1. `price_history` holds **only real prices the user entered** at checkout. Stats and
   predictions derive from it; never write predicted/catalog prices here.
2. `predicted_price()` ([app/pricing.py](app/pricing.py)) returns the user's **most recent**
   paid price for an item (a correction takes effect immediately — it is *not* an average).
3. `global_products` (the scraped Shufersal catalog) is a **fallback only**: it fills an
   estimate for items the user has never bought, and supplies variant suggestions. It must
   never override a real personal price.

`normalize_name()` ([app/pricing.py](app/pricing.py)) is the shared matching key across the
bot, pricing, and catalog matching — the same product must always normalize identically.

### Variant picker (generic terms → specific products)
When a typed term is generic (e.g. "פלפל"), [app/global_prices.py](app/global_prices.py)
finds catalog variants and `enrich_item_with_global()` (in services) flags the item
`needs_choice=True` and attaches `ItemSuggestion` rows grouped by category. The web list
shows a yellow picker; choosing one calls `resolve_variant` (or `resolve_custom_variant`
for free text), which rewrites the item and records the choice in `UserProduct`. Remembered
picks are re-offered first next time but the picker is always shown — it never auto-resolves.
Matching uses an `ILIKE '%token%'` prefilter (trigram-indexed on Postgres) plus a
**whole-word** post-filter so "שוקו" does not match "שוקולד".

### Data model ([app/models.py](app/models.py))
`User → ShoppingList → Item` (cascade delete). `Item.from_pending` marks carry-over items;
`Item.needs_choice` + `ItemSuggestion` drive the picker; `PendingItem` holds items carried
from a list ended before purchase; `PriceHistory` is the personal price record;
`GlobalProduct`/`UserProduct` back the catalog + remembered picks. Web pages are reached
only via unguessable tokens (`ShoppingList.web_token`, `User.stats_token`) — there is no
login.

### Migrations and dialect guards
Migrations are hand-numbered `0001_…` through `000N_…` in `migrations/versions/`. The test
suite runs on **SQLite in-memory**, so any Postgres-only DDL (e.g. the `pg_trgm` extension
and GIN index in `0006_global_products`) must be guarded with
`if bind.dialect.name == "postgresql"`.

### i18n
Hebrew (default) + English, in **two separate catalogs**:
[app/bot/i18n.py](app/bot/i18n.py) and [app/web/i18n.py](app/web/i18n.py). When adding a
user-facing string, add both languages to the relevant catalog. The chosen language is
persisted on `User.language` and shared between bot and web.

## Deployment

Deployment is **pull-based**: a host cron on the VPS runs
[scripts/auto_deploy.sh](scripts/auto_deploy.sh) every minute, which checks
`origin/main` and, when it moves, runs `git reset --hard origin/main` +
`docker compose up -d --build` and pings the admin on Telegram. **A merge to `main`
auto-deploys** (within ~1 min) — there is no separate release step and GitHub does
**not** SSH into the VPS. See [docs/auto-deploy-cron.md](docs/auto-deploy-cron.md).
The `price-fetch` job is a separate host cron, not the compose stack; see
[docs/price-fetch-cron.md](docs/price-fetch-cron.md).

## Git conventions

Built-in git-workflow instructions are disabled for this setup, so follow these when
committing on the user's behalf:
- **`main` auto-deploys.** Never commit or push to `main` without explicit approval —
  a push triggers the VPS deploy. Branch first, then open a PR.
- End commit messages with a trailer: `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Don't use `--no-verify` or skip hooks unless asked.

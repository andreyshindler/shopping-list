# Daily price fetch (global product catalog)

The bot enriches lists with prices and variant suggestions from a **shared global
product catalog** (`global_products`), refreshed daily from the Shufersal price feed.

The job is `app.jobs.fetch_prices`. It downloads the store's `PriceFull` files,
normalizes the Hebrew product names, and **replaces** the catalog snapshot in one
transaction. It is a one-shot process — there is no long-running scheduler.

## Configuration

Set these in `.env` (defaults in [`.env.example`](../.env.example)):

| Variable | Default | Meaning |
|----------|---------|---------|
| `SHUFERSAL_STORE_ID` | `7290027600007` | Store whose price files are fetched |
| `PRICE_FETCH_MAX_FILES` | `5` | Max PriceFull files to download per run |
| `GLOBAL_PRICE_CURRENCY` | `ILS` | Currency stored on catalog rows |

## Run it manually

```bash
docker compose run --rm price-fetch
```

The `price-fetch` service is behind the `jobs` compose profile, so a normal
`docker compose up -d` does **not** start it.

## Schedule it (host cron, one-time setup on the VPS)

Cron lives on the host, so it is provisioned once per machine (it is **not** part of
the push-to-deploy GitHub Action). Run `scripts/install-cron.sh`, or add this line
with `crontab -e` (adjust the repo path):

```cron
30 4 * * *  cd /root/projects/shopping-list && /usr/bin/docker compose run --rm price-fetch >> /var/log/price-fetch.log 2>&1
```

This refreshes the catalog every day at 04:30. Check the last run with:

```bash
tail -n 20 /var/log/price-fetch.log
```

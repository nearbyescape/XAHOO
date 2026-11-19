# Deploying XAHOO on the VPS

Runs next to the other sites: nginx on the host handles HTTPS for `xahoo.chaliyaboy.com` and forwards to the
container on `127.0.0.1:8010`. The certificate from certbot is already in place.

## 1. Replace the old version (one time)

```bash
cd /opt/xahoo
docker compose down                      # stops and removes the old v1 container
git fetch origin
git checkout main
git pull origin main
```

Edit `.env` (keep it `chmod 600`). Only these are used now; the Telegram lines can be deleted:

```
XAHOO_ADMIN_PASSWORD=...     # keep your existing one
XAHOO_SECRET=...             # keep your existing one
XAHOO_TOTP_SECRET=           # optional 2-step login
```

## 2. Allow the live WebSocket through nginx (one time)

Find the site file: `grep -l xahoo.chaliyaboy.com /etc/nginx/sites-enabled/*`
In its `server { listen 443 ... }` block, make the `location /` look like this:

```nginx
location / {
    proxy_pass http://127.0.0.1:8010;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

Then `sudo nginx -t && sudo systemctl reload nginx`.

Check it (expect **403** — the WebSocket handshake reached XAHOO and was refused only because curl is not
logged in; **303** or **400** means nginx is still not passing the upgrade):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" https://xahoo.chaliyaboy.com/ws
```

Without the upgrade the screen still works: it falls back to HTTPS updates every 1.5 s and the status badge
shows "LIVE · HTTPS" in amber instead of green.

## 3. Build and start

```bash
cd /opt/xahoo
docker build --network=host -t xahoo:latest .     # 3–6 minutes the first time
docker compose up -d --no-build
docker logs -f xahoo                               # Ctrl+C to stop watching
```

In the log you should see, within about a minute:
`backfilled BTCUSDT: 10579 bars …` for all ten markets, then `stream connected (30 streams)`.
Forecasts start at the next full minute. Open https://xahoo.chaliyaboy.com and log in.

Quick checks:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/robots.txt    # 200
docker stats --no-stream xahoo                                              # ~150–300 MB, under 1 CPU
```

## 4. Updating later

```bash
cd /opt/xahoo && git pull origin main
docker build --network=host -t xahoo:latest . && docker compose up -d --no-build
```

The scoreboard lives in the `xahoo-data` Docker volume and survives updates.

## Notes
- Live data: Binance public endpoints `fapi.binance.com` (REST) and `wss://fstream.binance.com/market/...`
  (WebSocket; Binance retired the unrouted stream URL on 2026-04-23); no API key. If the stream goes silent for
  60 s the server reconnects and logs "stream silent".
- If a market's backfill fails, the server retries every 3 minutes and also fills any bars missed during
  reconnects.
- Limits: 1 CPU, 1 GB memory (see `docker-compose.yml`).

## Research recorder (order book, single trades, liquidations)

Live mode saves one row per market per minute to `/data/micro.db` (the `xahoo-data` volume), with the data
Binance does not archive: order-book depth and imbalance at 0.1–2% from the mid, the largest walls, single-trade
counts and big trades, liquidations and the predicted funding rate. About 7 MB a day; it survives rebuilds.

- Progress (while logged in): `https://<your-domain>/api/micro` shows rows, days covered and rows per market.
- Turn it off: add `XAHOO_RECORD=0` to `.env` and restart.
- Copy it out for research: `docker cp xahoo:/data/micro.db ~/micro.db`

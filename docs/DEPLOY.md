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
- Live data: Binance public endpoints `fapi.binance.com` (REST) and `fstream.binance.com` (WebSocket); no API key.
- If a market's backfill fails, the server retries every 3 minutes and also fills any bars missed during
  reconnects.
- Limits: 1 CPU, 1 GB memory (see `docker-compose.yml`).

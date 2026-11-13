# Deploy XAHOO on the shared VPS: https://xahoo.chaliyaboy.com

XAHOO runs as **one extra container** next to NearbyEscape and XP. It listens only on `127.0.0.1:8010`, uses at most
1 CPU / 1 GB RAM, and your **existing** reverse proxy sends `xahoo.chaliyaboy.com` to it. Nothing about the other sites
changes except one new site block.

## 0. Look before changing anything (read-only)

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'      # what runs today
sudo ss -ltnp | grep -E ':(80|443|8010)\b'                          # who owns 80/443; is 8010 free?
free -h && df -h /                                                   # need ~1 GB RAM and ~2 GB disk free
```
- 80/443 owned by **nginx** (a host process) → use step 5A. By a **traefik** container → 5B. By **caddy** → 5C.
- If 8010 is taken, pick another port: add `XAHOO_PORT=8011` to `.env` and use that number below.

## 1. DNS
In the DNS of **chaliyaboy.com**, add an **A record**: `xahoo` → your VPS IP (same IP as the other sites).
If the domain is on Cloudflare, leave it **DNS only (grey cloud)** until HTTPS works, then you may switch on the proxy.
Check: `dig +short xahoo.chaliyaboy.com` shows the VPS IP.

## 2. Get the code (read-only deploy key)
```bash
sudo mkdir -p /opt/xahoo && sudo chown $USER /opt/xahoo
ssh-keygen -t ed25519 -f ~/.ssh/xahoo_deploy -N "" -C xahoo-vps
cat ~/.ssh/xahoo_deploy.pub
```
GitHub → `nearbyescape/XAHOO` → Settings → Deploy keys → *Add* → paste the key, **leave "Allow write access" off**.
```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/xahoo_deploy" \
  git clone -b main git@github.com:nearbyescape/XAHOO.git /opt/xahoo
cd /opt/xahoo && git config core.sshCommand "ssh -i ~/.ssh/xahoo_deploy"
```

## 3. Settings
```bash
cp .env.example .env && chmod 600 .env
openssl rand -hex 32          # paste as XAHOO_SECRET
nano .env
```
Set at least:
- `XAHOO_DOMAIN=xahoo.chaliyaboy.com`
- `XAHOO_ADMIN_PASSWORD=` a long passphrase, used for nothing else
- `XAHOO_SECRET=` the random string from above
- optional: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; `XAHOO_PREALERTS=on|off`

Optional 2-step login (recommended):
```bash
docker build --network=host -t xahoo:latest . && \
  docker run --rm xahoo:latest python -m xahoo.security
```
Put the printed `XAHOO_TOTP_SECRET=…` into `.env` and add the key to Google Authenticator / Authy.

## 4. Start XAHOO
```bash
docker build --network=host -t xahoo:latest .
docker compose -f deploy/docker-compose.vps.yml up -d --no-build
docker logs -f xahoo                         # first start downloads ~55 days of history (a few minutes)
curl -si http://127.0.0.1:8010/robots.txt | head -3   # expect: HTTP/1.1 200 OK
```

## 5. Connect the existing reverse proxy (pick ONE)

### 5A. Nginx on the host (most common)
```bash
sudo cp deploy/nginx/xahoo.chaliyaboy.com.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/xahoo.chaliyaboy.com.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx          # reloads ONLY if the test passes, so other sites are safe
sudo certbot --nginx -d xahoo.chaliyaboy.com          # HTTPS + auto-renew
```
(If your nginx uses `/etc/nginx/conf.d/` instead of `sites-available`, copy the file there as `xahoo.conf`.)

### 5B. Traefik in Docker
Edit `deploy/traefik.override.yml`: set the network name (`docker network ls`) and your certresolver name, then:
```bash
docker compose -f deploy/docker-compose.vps.yml -f deploy/traefik.override.yml up -d --build
```

### 5C. Caddy
Append `deploy/Caddyfile.snippet` to the existing Caddyfile and reload Caddy.

## 6. Check
1. Open **https://xahoo.chaliyaboy.com**. You should get the XAHOO login page (padlock shown).
2. `curl -s https://xahoo.chaliyaboy.com/robots.txt` → `Disallow: /`
3. Log in → header shows **LIVE · swissquote**. Signals start after ~2.5 h of live data ("warming up").
4. Phone: open the site → install it (Android: menu → *Install app*; iPhone: Share → *Add to Home Screen*) →
   open the app → tap 🔕 → allow. A test alert should pop up within seconds.

## 7. Day-to-day
| Task | Command (in `/opt/xahoo`) |
|---|---|
| Update | `git pull && docker build --network=host -t xahoo:latest . && docker compose -f deploy/docker-compose.vps.yml up -d --no-build` |
| Logs | `docker logs --tail 200 xahoo` |
| Restart | `docker restart xahoo` |
| Stop | `docker compose -f deploy/docker-compose.vps.yml down` |
| Backup | `cp data/live.db data/live.db.$(date +%F)` (signals, alerts, settings; also back up `.env` and `data/vapid_private.pem`) |
| Resource use | `docker stats xahoo --no-stream` |

Rollback: `docker compose -f deploy/docker-compose.vps.yml down` and remove the nginx site link
(`sudo rm /etc/nginx/sites-enabled/xahoo.chaliyaboy.com.conf && sudo nginx -t && sudo systemctl reload nginx`).
The other sites are untouched.

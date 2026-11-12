# Deploying on Railway

One Railway project with four services: **web**, **gamehost**, **Postgres** and **Redis**.
`web` and `gamehost` build the same `Dockerfile` from this repo; only the start command differs.
Expected cost on the Hobby plan: about $5 to $10 a month for a few games at a time.

## 1. Create the project

1. Sign in at <https://railway.com> with GitHub and choose the **Hobby** plan.
2. **New Project → Deploy PostgreSQL**. Then in the same project **+ New → Database → Redis**.
   Keep their default service names `Postgres` and `Redis` (the variables below refer to them).

## 2. Web service

1. **+ New → GitHub Repo →** `emersonjleon/island`. Rename the service to `web`.
2. **Settings → Config-as-code → Railway config file:** `deploy/railway/web.json`.
   This builds the Dockerfile, runs `migrate` before every deploy, and starts Daphne on `$PORT`.
3. **Settings → Networking → Generate Domain.** Note it, e.g. `island-production.up.railway.app`.
4. **Variables** (raw editor):

   ```
   DJANGO_SECRET_KEY=<a long random string, e.g. from: python -c "import secrets; print(secrets.token_urlsafe(50))">
   DJANGO_ALLOWED_HOSTS=island-production.up.railway.app
   DJANGO_CSRF_TRUSTED_ORIGINS=https://island-production.up.railway.app
   DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
   POSTGRES_HOST=${{Postgres.PGHOST}}
   POSTGRES_PORT=${{Postgres.PGPORT}}
   POSTGRES_DB=${{Postgres.PGDATABASE}}
   POSTGRES_USER=${{Postgres.PGUSER}}
   POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}
   REDIS_URL=${{Redis.REDIS_URL}}
   ```

   Use your own domain in the two `DJANGO_*` host lines. The console email backend only logs
   emails (e.g. password resets); switch to an SMTP service later by setting
   `DJANGO_EMAIL_BACKEND` back to the SMTP backend plus Django's `EMAIL_*` settings.

## 3. Game host service

1. **+ New → GitHub Repo →** `emersonjleon/island` again. Rename it to `gamehost`.
2. **Settings → Config-as-code → Railway config file:** `deploy/railway/gamehost.json`.
   It starts `python manage.py run_gamehost`, keeps exactly one replica and always restarts it.
3. No public domain: it only talks to Redis and Postgres.
4. **Variables:** the same list as `web` (the host lines are harmless here). Tip: put them in
   **Project Settings → Shared Variables** once and share them with both services.

Keep `gamehost` at one replica. A second copy would compete for the same games.

## 4. Check it

1. Wait for both deploys to go green. The web deploy logs show the migrations.
2. Open the domain, sign up, create a game, and join from a second browser (or a friend).
3. The `gamehost` logs should show the game starting and dice rolls.

## 5. Keep the bill in check

**Workspace → Usage → Usage limits**: set a hard limit, e.g. $10. Railway stops services when it is hit.

## Updating

Every push to `main` redeploys both services. On redeploy the game host gets SIGTERM, snapshots
every live game, and the new one resumes them; players see a short pause.

## Other Docker hosts

The image works anywhere Docker runs: `docker run -p 8000:8000 <env vars> image` for the web
process, and the same image with `python manage.py run_gamehost` for the game host, plus
Postgres and Redis reachable through the variables above.

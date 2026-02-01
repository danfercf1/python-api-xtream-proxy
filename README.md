# Project

## Python virtual environment (local)

Create the environment:

```bash
python3 -m venv .venv
```

Activate it (Linux/macOS):

```bash
source .venv/bin/activate
```

Activate it (Windows PowerShell):

```bash
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run locally (without Docker)

If your `.env` uses `PORT=80`, running `python3 app.py` on Linux will fail with `Permission denied` (ports <1024 require root).

For local testing, set a non-privileged port in `.env`, for example:

```bash
PORT=5000
```

## How to create a mysql backup

* Create the backup

```bash
docker exec <container_id> mariadb-dump -u<username> -p<password> <database_name> > ./mysql_backups/"$(date +'%Y-%m-%d')_backup.sql"
```

### Using the helper script

This repo includes `scripts/backup_db.sh` which writes a timestamped dump into `./mysql_backups/`.

```bash
./scripts/backup_db.sh --env .env
```

If your DB container isn’t discoverable automatically, pass it explicitly:

```bash
./scripts/backup_db.sh --env .env --container <container_id_or_name>
```

* To restore the dabase

First copy the sql to the container

```bash
docker cp /path/to/backup.sql container_name:/path/inside/container/backup.sql

```

Then restore the database

```bash
docker exec <container_id> sh -c 'exec mariadb -uroot -p<password> xtream_code < /2024-03-11_backup.sql'
```

## Add a user to the DB

You can insert a user into the `users` table using:

```bash
./scripts/add_user.sh --env .env --username <username> --password <password>
```

If needed, specify the DB container explicitly:

```bash
./scripts/add_user.sh --env .env --container <container_id_or_name> --username <username> --password <password>
```

## Add the crontab configuration to run the update scripts

Add the livestream category cronjob to run every day using crontab -e

```bash
0 0 * * 0 docker exec python-api-xtream-proxy-api-1 python ./sync/sync_data_live_categories.py >> ~/logs/sync_data_live_categories.log 2>&1
```

Check if the crontab is added

```bash
crontab -l
```

Add the livestream cronjob to run every week using crontab -e

```bash
0 0 * * * docker exec python-api-xtream-proxy-api-1 python ./sync/sync_data_live_streams.py >> ~/logs/sync_data_live_streams.log 2>&1
```

Check if the crontab is added

```bash
crontab -l
```

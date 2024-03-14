# Project

## How to create a mysql backup

* Create the backup

```bash
docker exec <container_id> mariadb-dump -u<username> -p<password> <database_name> > ./mysql_backups/"$(date +'%Y-%m-%d')_backup.sql"
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

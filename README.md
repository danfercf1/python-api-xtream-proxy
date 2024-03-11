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

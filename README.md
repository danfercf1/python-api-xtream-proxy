# Project

## How to create a mysql backup

* Create the backup

```bash
docker exec <container_id> mariadb-dump -u<username> -p<password> <database_name> > ./mysql_backups/"$(date +'%Y-%m-%d')_backup.sql"
```

* To restore the dabase

```bash
docker exec <container_id> sh -c 'exec mariadb -uroot -p<password> < ./mysql_backups/backup.sql
```

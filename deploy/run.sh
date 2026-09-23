#!/bin/bash
# Supervisor: cron runs this every minute; flock keeps a single instance.
cd /home/sleepy/dozer || exit 1
exec 9>/home/sleepy/dozer/logs/.lock
flock -n 9 || exit 0
echo "$(date -u +%FT%TZ) supervisor: starting Dozer" >> logs/stdout.log
exec venv/bin/python main.py >> logs/stdout.log 2>&1

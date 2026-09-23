#!/bin/bash
# Interim supervisor (used until dozer.service is installed): restarts Dozer if it exits.
cd /home/sleepy/dozer || exit 1
exec 9>/home/sleepy/dozer/logs/.lock
flock -n 9 || { echo "already running"; exit 0; }
while true; do
  echo "$(date -u +%FT%TZ) supervisor: starting Dozer" >> logs/stdout.log
  venv/bin/python main.py >> logs/stdout.log 2>&1
  echo "$(date -u +%FT%TZ) supervisor: Dozer exited ($?), restarting in 5s" >> logs/stdout.log
  sleep 5
done

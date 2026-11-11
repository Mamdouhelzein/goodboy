---
name: log-analysis
description: "Analyze server logs (auth.log, syslog, Apache/Nginx access logs, Windows event logs) to find brute-force attempts, suspicious IPs, and anomalies."
---

# Log Analysis

Analyze server logs (auth.log, syslog, Apache/Nginx access logs, Windows event logs) to find brute-force attempts, suspicious IPs, and anomalies.

## Auth logs

grep 'Failed password' /var/log/auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -nr

## Web logs

Look for 4xx spikes, scanners' user agents, path traversal and SQLi patterns in request lines.

## Timeline

Normalize timestamps to UTC and build a per-IP timeline of events.

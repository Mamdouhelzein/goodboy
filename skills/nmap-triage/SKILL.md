---
name: nmap-triage
description: "Triage nmap or other port-scanner output: flag risky open ports and services, explain the exposure, and recommend how to close or harden each one."
---

# Nmap Triage

Triage nmap or other port-scanner output: flag risky open ports and services, explain the exposure, and recommend how to close or harden each one.

## Reading scan output

Parse `nmap -sV -oX` XML or grepable output. List host, port, protocol, service and version.

## Risk rules

Telnet (23), FTP (21), SMB (445), RDP (3389), exposed databases (3306, 5432, 27017, 6379) and outdated service versions are high risk.

## Hardening

Close unused ports with ufw or iptables, bind databases to localhost, disable anonymous FTP, require SSH keys.

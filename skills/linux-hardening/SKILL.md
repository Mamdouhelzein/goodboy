---
name: linux-hardening
description: "Harden a Linux server: SSH configuration, firewall rules, automatic updates, fail2ban, users and permissions."
---

# Linux Hardening

Harden a Linux server: SSH configuration, firewall rules, automatic updates, fail2ban, users and permissions.

## SSH

Disable root login and password auth in sshd_config, use keys, change nothing else blindly.

## Firewall

ufw default deny incoming; allow only needed ports.

## Maintenance

unattended-upgrades, fail2ban for sshd, audit sudoers and SUID binaries.

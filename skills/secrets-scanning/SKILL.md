---
name: secrets-scanning
description: "Find leaked secrets such as API keys, tokens and passwords in code and git history, then rotate them and scrub the history."
---

# Secrets Scanning

Find leaked secrets such as API keys, tokens and passwords in code and git history, then rotate them and scrub the history.

## Scan

Run gitleaks or trufflehog over the repo and the full history.

## Respond

Revoke and rotate the credential first, then remove it with git filter-repo and force-push.

## Prevent

Add a pre-commit hook and move secrets to environment variables or a vault.

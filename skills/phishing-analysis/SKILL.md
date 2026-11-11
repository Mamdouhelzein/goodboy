---
name: phishing-analysis
description: "Investigate a suspicious or phishing email: read the headers, check SPF/DKIM/DMARC, inspect links and attachments safely, and decide if it is malicious."
---

# Phishing Analysis

Investigate a suspicious or phishing email: read the headers, check SPF/DKIM/DMARC, inspect links and attachments safely, and decide if it is malicious.

## Headers

Trace Received: hops, compare From, Reply-To and Return-Path, read Authentication-Results.

## Links

Defang URLs, expand shorteners, check domains against lookalikes and reputation services.

## Attachments

Never open; hash them and check the hash, inspect macros with olevba in a sandbox.

---
name: api-testing
description: "Test REST APIs: send requests with curl or Python requests, write pytest API tests, check status codes, auth and JSON schemas."
---

# Api Testing

Test REST APIs: send requests with curl or Python requests, write pytest API tests, check status codes, auth and JSON schemas.

## Manual

curl -i -H 'Authorization: Bearer ...' to inspect responses.

## Automated

pytest with requests or httpx; fixtures for auth tokens.

## Checks

Status codes, schema validation, error cases, rate limits.

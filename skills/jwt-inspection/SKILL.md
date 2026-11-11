---
name: jwt-inspection
description: "Decode, inspect and validate JSON Web Tokens (JWT): check the algorithm, signature, expiry and claims, and spot common JWT vulnerabilities."
---

# Jwt Inspection

Decode, inspect and validate JSON Web Tokens (JWT): check the algorithm, signature, expiry and claims, and spot common JWT vulnerabilities.

## Decode

Split on dots and base64url-decode header and payload; never trust them before verifying.

## Flaws

alg=none, HS256/RS256 confusion, weak HMAC secrets, missing exp or aud checks.

## Verify

Use PyJWT with an explicit algorithms list and required claims.

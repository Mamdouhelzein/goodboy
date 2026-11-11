---
name: docker-hardening
description: "Secure Docker images and containers: Dockerfile best practices, running as non-root, minimal base images, and scanning images for vulnerabilities."
---

# Docker Hardening

Secure Docker images and containers: Dockerfile best practices, running as non-root, minimal base images, and scanning images for vulnerabilities.

## Dockerfile

Pin base image digests, use multi-stage builds, add USER for a non-root user.

## Runtime

Drop capabilities, read-only root filesystem, no --privileged, limit memory and CPU.

## Scanning

Scan with trivy image or docker scout cves.

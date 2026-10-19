# TechAbout Dockerfile Audit

Audit of 3 sample Dockerfiles (Python, Node.js, Go): problems found, fixed versions, and measured size comparison.

## Contents

- `samples/app-python/` - Flask app: `Dockerfile.before` (flawed) vs `Dockerfile.after` (fixed)
- `samples/app-node/` - Express app: `Dockerfile.before` vs `Dockerfile.after`
- `samples/app-go/` - Go net/http service: `Dockerfile.before` vs `Dockerfile.after`
- `docs/AUDIT.md` - every problem found, why it matters, and how it was fixed
- `docs/BEST_PRACTICES.md` - 12-rule shortlist for the team
- `scripts/build-compare.sh` - builds all 6 images and prints the size table

## Runbook

Prereqs: Docker Engine 24+ on your own machine. Never run this against company or third-party systems.

```bash
# 1. build everything and print the size comparison
./scripts/build-compare.sh

# 2. smoke-test a fixed image (example: python)
docker run -d --name audit-py -p 5000:5000 audit-python-after
curl localhost:5000/health        # {"status":"healthy"}
docker stop audit-py && docker rm audit-py

# 3. compare one pair by hand
docker build -f samples/app-go/Dockerfile.before -t go-before samples/app-go
docker build -f samples/app-go/Dockerfile.after  -t go-after  samples/app-go
docker images go-before go-after
```

## Results (measured 2026-10-19, `docker images`)

| Sample | Before | After | Reduction |
|--------|--------|-------|-----------|
| app-python | 1.2GB | 136MB | 88.7% |
| app-node | 1.25GB | 230MB | 81.6% |
| app-go | 893MB | 81.9MB | 90.8% |

Key wins: pinned slim base images (`python:3.12-slim-bookworm`, `node:22-bookworm-slim`, `debian:12-slim`), multi-stage Go build, no `latest` tags, non-root users, `.dockerignore` files, exec-form CMD/ENTRYPOINT, HEALTHCHECKs, no leaked secrets.

## Notes

- No secrets anywhere in this repo. The `ENV API_KEY` / `ENV STRIPE_KEY` lines in the `.before` files are obviously fake placeholders (`sk-live-abc123`) included only to demonstrate the anti-pattern.
- AI tools were used for drafting; every line was reviewed and the builds were run by hand.

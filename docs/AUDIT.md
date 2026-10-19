# Dockerfile Audit: problems found

## Sample 1: app-python (Flask)

| # | Problem | Why it matters | Fixed in `Dockerfile.after` |
|---|---------|----------------|-----------------------------|
| P1 | `FROM python:latest` | Mutable tag: rebuilds silently change the interpreter, builds are not reproducible | Pinned `python:3.12-slim-bookworm` |
| P2 | `COPY . .` before `pip install` | Any code change invalidates the dependency layer, every build reinstalls everything | Copy `requirements.txt` first, install, then copy code |
| P3 | No `.dockerignore` effect (copies `.git`, `__pycache__`, `.env`) | Bloats the image, can leak secrets and history into layers | Added `.dockerignore` |
| P4 | `apt-get install` without cleanup | Leaves ~100MB+ of package lists in the layer | Slim base needs no apt at all; removed |
| P5 | `pip install` without `--no-cache-dir` | Wheel cache stays in the image | `PIP_NO_CACHE_DIR=1` + `--no-cache-dir` |
| P6 | `ENV API_KEY="sk-live-..."` | Secret baked into image history forever, visible to anyone who pulls it | Removed; secrets must come from runtime env / secret stores |
| P7 | Runs as root | A container escape or RCE runs with full privileges | Dedicated `appuser` (uid 10001), `USER appuser` |
| P8 | `CMD python app.py` (shell form) | PID 1 is `sh`, signals don't reach the app, `docker stop` waits the full timeout | Exec form `CMD ["python", "app.py"]` |
| P9 | No `HEALTHCHECK` | Orchestrator can't tell a hung app from a healthy one | Added curl-free healthcheck against `/health` |

## Sample 2: app-node (Express)

| # | Problem | Why it matters | Fixed in `Dockerfile.after` |
|---|---------|----------------|-----------------------------|
| N1 | `FROM node:latest` | Same reproducibility problem as P1 | Pinned `node:22-bookworm-slim` |
| N2 | `COPY . .` first (drags host `node_modules`) | Host-built binaries (wrong arch) can end up in the image | `.dockerignore` + copy manifests first |
| N3 | `npm install` instead of `npm ci` | Installs whatever resolves today, not what was tested | `npm ci` against committed `package-lock.json` |
| N4 | devDependencies in production image | Bigger image, bigger attack surface | `--omit=dev` |
| N5 | `npm install -g nodemon` in prod image | Dev tooling shipped to production | Removed entirely |
| N6 | `ENV STRIPE_KEY=...` baked in | Same secret-leak problem as P6 | Removed |
| N7 | Runs as root | Same as P7 | `USER appuser` |
| N8 | Single stage, full toolchain in final image | npm, build tools ship for no reason | Multi-stage: deps stage + slim runtime stage |
| N9 | `CMD npm start` (shell form) | Same signal problem as P8 | Exec form `CMD ["node", "server.js"]` |
| N10 | No `HEALTHCHECK` | Same as P9 | Added fetch-based healthcheck |

## Sample 3: app-go (net/http)

| # | Problem | Why it matters | Fixed in `Dockerfile.after` |
|---|---------|----------------|-----------------------------|
| G1 | `FROM golang:latest` | Same reproducibility problem as P1 | Pinned `golang:1.22-bookworm` for build |
| G2 | Single-stage build | The ~1GB Go toolchain, module cache and source ship in the final image | Multi-stage: build in Go image, ship only the binary |
| G3 | Unstripped binary, CGO default | Larger binary, needs libc in runtime | `CGO_ENABLED=0`, `-trimpath -ldflags="-s -w"` |
| G4 | Runs as root | Same as P7 | `debian:12-slim` + dedicated `appuser` (uid 10001) |
| G5 | `CMD ./server` (shell form) | Same signal problem as P8 | `ENTRYPOINT ["/server"]` exec form |
| G6 | No `HEALTHCHECK` | Same as P9 | (slim base keeps it simple; health checked by orchestrator probe against `/health`) |

## Cross-cutting notes

- Every "before" image also lacks a pinned digest. For supply-chain safety, pin `image:tag@sha256:...` in production.
- None of the "before" Dockerfiles set a `WORKDIR` consistently or drop capabilities; the "after" versions run as non-root, which is the single highest-value hardening step.
- Secrets: none of the sample apps need real secrets; the audit removes the baked-in ones and documents that secrets must arrive at runtime (env from a secret manager, mounted files), never via `ENV`/`ARG` in the Dockerfile.

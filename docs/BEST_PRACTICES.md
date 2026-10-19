# Dockerfile best practices (team shortlist)

1. **Pin your base image.** `python:3.12-slim-bookworm`, never `latest`. For production, pin the digest too: `image:tag@sha256:...`.
2. **Use small bases.** Prefer `-slim` / `-alpine` variants, or distroless for compiled languages. Smaller image = faster pulls, fewer CVEs.
3. **Order layers by change frequency.** Copy dependency manifests first, install, then copy code. Keeps rebuilds fast.
4. **Always add `.dockerignore`.** Keep `.git`, `node_modules`, `__pycache__`, `.env` out of the build context and the image.
5. **Multi-stage builds.** Build tools in one stage, ship only the artifact in the final stage.
6. **Never bake secrets into images.** No `ENV API_KEY=...`, no `ARG` secrets (they persist in history). Inject at runtime from a secret manager or mounted files.
7. **Run as non-root.** Create a dedicated user and set `USER`. It's the cheapest hardening win.
8. **Exec form for CMD/ENTRYPOINT.** `CMD ["node", "server.js"]`, not `CMD npm start`, so signals reach your app.
9. **Clean up in the same layer.** `apt-get ... && rm -rf /var/lib/apt/lists/*`, `pip install --no-cache-dir`, `npm ci --omit=dev`.
10. **Add a HEALTHCHECK** (or orchestrator probe) so unhealthy containers get restarted instead of serving traffic.
11. **One process per container.** Don't bundle app + cron + nginx in one image; compose them instead.
12. **Scan before you ship.** Run `docker scout` / Trivy in CI and fail the build on critical CVEs.

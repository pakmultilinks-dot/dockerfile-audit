#!/usr/bin/env python3
"""Download a Docker image via the registry API (through the egress proxy) and
save it as a `docker load`-compatible tarball."""
import hashlib
import io
import json
import os
import sys
import tarfile

import requests

OUTDIR = os.path.expanduser("~/workspace/dockerfile-audit/images")
os.makedirs(OUTDIR, exist_ok=True)


def token_for(registry, repo):
    if registry == "registry-1.docker.io":
        url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
        return requests.get(url, timeout=30).json()["token"]
    if registry == "gcr.io":
        # public gcr.io images: try anonymous token
        url = f"https://gcr.io/v2/token?service=gcr.io&scope=repository:{repo}:pull"
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        return None
    return None


def fetch_image(ref, repo_tag):
    """ref like registry-1.docker.io/library/python:3.12-slim-bookworm"""
    registry, rest = ref.split("/", 1)
    repo, tag = rest.rsplit(":", 1)
    token = token_for(registry, repo)
    H = {}
    if token:
        H["Authorization"] = f"Bearer {token}"
    print(f"== {ref} -> {repo_tag}", flush=True)

    def get(url, accept):
        h = dict(H)
        h["Accept"] = accept
        r = requests.get(url, headers=h, timeout=120)
        r.raise_for_status()
        return r

    # manifest (handle index -> pick amd64)
    m = get(f"https://{registry}/v2/{repo}/manifests/{tag}",
            "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.docker.distribution.manifest.v2+json").json()
    if m.get("mediaType", "").endswith("index.v1+json") or "manifests" in m:
        amd = [x for x in m["manifests"]
               if x["platform"]["architecture"] == "amd64"
               and x["platform"].get("os") == "linux"][0]
        digest = amd["digest"]
        m = get(f"https://{registry}/v2/{repo}/manifests/{digest}",
                "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json").json()

    config_digest = m["config"]["digest"]
    layers = m["layers"]

    # download config
    cfg = get(f"https://{registry}/v2/{repo}/blobs/{config_digest}", "application/octet-stream").content
    cfg_sha = hashlib.sha256(cfg).hexdigest()

    # build docker-load tarball in memory
    buf = io.BytesIO()
    tf = tarfile.open(fileobj=buf, mode="w")
    layer_files = []
    total = sum(l["size"] for l in layers)
    done = 0
    for i, layer in enumerate(layers):
        digest = layer["digest"]
        data = get(f"https://{registry}/v2/{repo}/blobs/{digest}", "application/octet-stream").content
        name = digest.split(":")[1]
        arc = f"{name}/layer.tar"
        ti = tarfile.TarInfo(arc)
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))
        # VERSION file per layer dir (docker load wants it)
        v = b"1.0"
        ti2 = tarfile.TarInfo(f"{name}/VERSION")
        ti2.size = len(v)
        tf.addfile(ti2, io.BytesIO(v))
        # json per layer dir
        lj = json.dumps({"id": name}).encode()
        ti3 = tarfile.TarInfo(f"{name}/json")
        ti3.size = len(lj)
        tf.addfile(ti3, io.BytesIO(lj))
        layer_files.append(arc)
        done += len(data)
        print(f"  layer {i+1}/{len(layers)} {len(data)//1024//1024}MB ({done//1024//1024}/{total//1024//1024}MB)", flush=True)

    # config file
    cfg_name = f"{cfg_sha}.json"
    ti = tarfile.TarInfo(cfg_name)
    ti.size = len(cfg)
    tf.addfile(ti, io.BytesIO(cfg))

    manifest = [{"Config": cfg_name, "RepoTags": [repo_tag], "Layers": layer_files}]
    mj = json.dumps(manifest).encode()
    ti = tarfile.TarInfo("manifest.json")
    ti.size = len(mj)
    tf.addfile(ti, io.BytesIO(mj))
    tf.close()

    out = os.path.join(OUTDIR, repo_tag.replace("/", "_").replace(":", "_") + ".tar")
    with open(out, "wb") as f:
        f.write(buf.getvalue())
    print(f"  saved {out} ({os.path.getsize(out)//1024//1024}MB)", flush=True)
    return out


if __name__ == "__main__":
    # pairs of (registry ref, docker tag for load)
    images = [
        ("registry-1.docker.io/library/python:latest", "python:latest"),
        ("registry-1.docker.io/library/python:3.12-slim-bookworm", "python:3.12-slim-bookworm"),
        ("registry-1.docker.io/library/node:latest", "node:latest"),
        ("registry-1.docker.io/library/node:22-bookworm-slim", "node:22-bookworm-slim"),
        ("registry-1.docker.io/library/golang:latest", "golang:latest"),
        ("registry-1.docker.io/library/golang:1.22-bookworm", "golang:1.22-bookworm"),
        ("registry-1.docker.io/library/debian:12-slim", "debian:12-slim"),
        ("gcr.io/distroless/static-debian12:nonroot", "gcr.io/distroless/static-debian12:nonroot"),
    ]
    only = sys.argv[1:]
    for ref, tag in images:
        if only and not any(o in ref for o in only):
            continue
        fetch_image(ref, tag)

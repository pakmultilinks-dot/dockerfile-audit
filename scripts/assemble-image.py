#!/usr/bin/env python3
"""Assemble a Docker image tarball from a base image tar + host-built layers.

Usage:
  assemble-image.py <base-tar> <output-tar> <repo-tag> --layer <dir>[:<desc>] ... [--env K=V ...] [--workdir D] [--user U] [--expose P ...] [--entrypoint CMD...] [--cmd CMD...]

Each --layer points a host directory whose contents become one image layer
(relative paths inside the dir map to absolute paths in the image).
Layer tarballs are written with pax headers compatible with `docker load`.
The image config is derived from the base image's config with updated
rootfs diff_ids, history, and container config.
"""
import argparse, hashlib, io, json, os, sys, tarfile, tempfile

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()

def make_layer_tar(srcdir, tmpdir, name):
    """Tar up srcdir contents as a docker layer. Returns (path, diff_id)."""
    out = os.path.join(tmpdir, name)
    with tarfile.open(out, "w", format=tarfile.PAX_FORMAT) as tf:
        for root, dirs, files in os.walk(srcdir):
            for fn in files:
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, srcdir)
                ti = tf.gettarinfo(full, arcname=arc)
                ti.name = arc
                # normalize ownership to root for reproducibility
                ti.uid, ti.gid, ti.uname, ti.gname = 0, 0, "", ""
                if ti.issym() or ti.islnk():
                    tf.addfile(ti)
                else:
                    with open(full, "rb") as f:
                        tf.addfile(ti, f)
            # ensure dirs exist (add explicit dir entries)
            for d in dirs:
                full = os.path.join(root, d)
                arc = os.path.relpath(full, srcdir)
                ti = tarfile.TarInfo(arc)
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                ti.uid, ti.gid, ti.uname, ti.gname = 0, 0, "", ""
                tf.addfile(ti)
    return out, "sha256:" + sha256_file(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_tar")
    ap.add_argument("output_tar")
    ap.add_argument("repo_tag")  # e.g. audit-python-after:latest
    ap.add_argument("--layer", action="append", default=[], help="host dir to add as a layer")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--user", default=None)
    ap.add_argument("--expose", action="append", default=[])
    ap.add_argument("--entrypoint", nargs=argparse.REMAINDER, default=None)
    ap.add_argument("--cmd", nargs="+", default=None)
    ap.add_argument("--healthcheck-test", nargs="+", default=None)
    args = ap.parse_args()

    tmpdir = tempfile.mkdtemp(prefix="assemble-")
    outdir = os.path.join(tmpdir, "out")
    os.makedirs(outdir, exist_ok=True)
    # read base tar manifest + config directly from the tar (v1 or v2 layout)
    with tarfile.open(args.base_tar) as tf:
        manifest = json.load(tf.extractfile("manifest.json"))
        ment = manifest[0]
        base_config_name = ment["Config"]
        config = json.load(tf.extractfile(base_config_name))
        # extract base layers to outdir, preserving their tar-internal paths
        for lf in ment["Layers"]:
            src = tf.extractfile(lf)
            dest = os.path.join(outdir, lf)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as d:
                d.write(src.read())
        base_layer_names = list(ment["Layers"])

    new_layer_files = []   # tar member names in output
    new_diff_ids = []
    new_history = []

    # build output tar
    # (outdir already has base layers; add new layers)
    for i, ldir in enumerate(args.layer):
        lname = f"layer-new-{i}.tar"
        lpath, diff_id = make_layer_tar(ldir, tmpdir, lname)
        dest = os.path.join(outdir, lname)
        os.rename(lpath, dest)
        new_layer_files.append(lname)
        new_diff_ids.append(diff_id)
        new_history.append({"created": "2026-10-19T00:00:00Z", "created_by": f"manual layer {i} ({ldir})", "empty_layer": False})

    # update config
    config.setdefault("rootfs", {})["diff_ids"].extend(new_diff_ids)
    config.setdefault("history", []).extend(new_history)
    cfg = config.setdefault("config", {})
    for e in args.env:
        cfg.setdefault("Env", []).append(e)
    if args.workdir:
        cfg["WorkingDir"] = args.workdir
    if args.user:
        cfg["User"] = args.user
    if args.expose:
        ports = cfg.setdefault("ExposedPorts", {})
        for p in args.expose:
            ports[f"{p}/tcp"] = {}
    if args.entrypoint:
        cfg["Entrypoint"] = args.entrypoint
    if args.cmd:
        cfg["Cmd"] = args.cmd
    if args.healthcheck_test:
        cfg["Healthcheck"] = {
            "Test": args.healthcheck_test,
            "Interval": 30000000000,
            "Timeout": 3000000000,
            "StartPeriod": 5000000000,
            "Retries": 3,
        }

    cfg_bytes = json.dumps(config, indent=2).encode()
    cfg_name = sha256_bytes(cfg_bytes) + ".json"
    with open(os.path.join(outdir, cfg_name), "wb") as f:
        f.write(cfg_bytes)

    repo, tag = args.repo_tag.split(":", 1)
    new_manifest = [{
        "Config": cfg_name,
        "RepoTags": [args.repo_tag],
        "Layers": base_layer_names + new_layer_files,
    }]
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(new_manifest, f)

    with tarfile.open(args.output_tar, "w", format=tarfile.PAX_FORMAT) as tf:
        for root, _, files in os.walk(outdir):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                tf.add(full, arcname=fn)
    print(f"wrote {args.output_tar} ({os.path.getsize(args.output_tar)//1024//1024}MB)")

if __name__ == "__main__":
    main()

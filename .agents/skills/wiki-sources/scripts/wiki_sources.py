#!/usr/bin/env python3
"""wiki_sources.py: incremental mirrors of git repositories used as wiki sources.

Each git source is declared in raw/sources.json with the upstream URL, what to
track (a branch, or the newest stable tag matching a pattern), the upstream
paths to mirror, the raw/ folder that mirrors them (same relative paths), and
the exact commit last ingested.

Nothing is cloned in full. Every operation works in a throwaway partial clone:

  check   git ls-remote only. Downloads no objects. Says which sources moved.
  diff    Fetches the two commits' trees (depth 1, blob:none) and lists the
          files that changed under the tracked paths. Downloads no file content.
  sync    Like diff, then fetches only the changed files' blobs in one batch,
          applies them to the raw mirror (add/modify/delete), and records the
          new commit. Prints the change set as JSON for the ingest step.
  add     First snapshot of a new source (sync from an empty tree).
  verify  Hashes the raw mirror with `git hash-object` and compares it to the
          recorded commit's tree. Reports drift; downloads trees only.

Usage (SCRIPT = path to this file):
  python3 SCRIPT [--root DIR] [--manifest FILE] check [ID ...] [--json]
  python3 SCRIPT [--root DIR] diff ID [--to REF]
  python3 SCRIPT [--root DIR] sync ID [--to REF] [--dry-run]
  python3 SCRIPT [--root DIR] add ID URL --raw-dir DIR --path P [--path P ...]
                 (--branch NAME | --tag-pattern GLOB [--include-prereleases])
                 [--source-page SLUG ...]
  python3 SCRIPT [--root DIR] verify ID

Root resolution (first match wins): --root, $WIKI_SOURCES_ROOT, the nearest
ancestor of the current directory that contains raw/sources.json, the git
top-level of the current directory, the current directory. The manifest is
<root>/raw/sources.json unless --manifest or $WIKI_SOURCES_MANIFEST says
otherwise. raw_dir values in the manifest are relative to the root; raw_dir
"." mirrors upstream paths at the root itself (used to install skills).

Requires only Python 3.9+ and git. Works from any agent that can run a shell.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
MANIFEST = ROOT / "raw" / "sources.json"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
BATCH = 400
STABLE_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
ANY_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(.*)$")


# ---------- helpers ----------

def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def git(*args: str, cwd: Path | None = None, input: str | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, input=input, text=True,
                       capture_output=True)
    if r.returncode != 0:
        die(f"git {' '.join(args[:3])} ... failed:\n{r.stderr.strip()}")
    return r.stdout


def load() -> dict:
    if not MANIFEST.exists():
        return {"version": 1, "sources": []}
    return json.loads(MANIFEST.read_text())


def save(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n")


def find(m: dict, sid: str) -> dict:
    for s in m["sources"]:
        if s["id"] == sid:
            return s
    die(f"unknown source id '{sid}'. Known: {', '.join(x['id'] for x in m['sources'])}")


def today() -> str:
    return dt.date.today().isoformat()


# ---------- remote resolution (ls-remote only) ----------

def resolve_remote(src: dict, to: str | None = None) -> tuple[str, str]:
    """Return (ref_name, commit_sha) of the target upstream revision."""
    url = src["url"]
    if to:
        out = git("ls-remote", url, to, f"refs/tags/{to}^{{}}", f"refs/tags/{to}", f"refs/heads/{to}")
        rows = [l.split("\t") for l in out.splitlines() if l]
        peeled = [r for r in rows if r[1].endswith("^{}")]
        if peeled:
            return to, peeled[0][0]
        if rows:
            return to, rows[0][0]
        if re.fullmatch(r"[0-9a-f]{40}", to):
            return to, to
        die(f"ref '{to}' not found on {url}")
    track = src["track"]
    if track["type"] == "branch":
        out = git("ls-remote", url, f"refs/heads/{track['name']}")
        if not out.strip():
            die(f"branch {track['name']} not found on {url}")
        return track["name"], out.split()[0]
    if track["type"] == "tag":
        out = git("ls-remote", "--tags", url)
        tags: dict[str, str] = {}
        for line in out.splitlines():
            sha, ref = line.split("\t")
            name = ref.removeprefix("refs/tags/")
            peeled = name.endswith("^{}")
            name = name.removesuffix("^{}")
            if not fnmatch.fnmatch(name, track.get("pattern", "*")):
                continue
            if peeled or name not in tags:
                tags[name] = sha
        rx = ANY_TAG if track.get("include_prereleases") else STABLE_TAG
        cands = [(tuple(int(x) for x in mm.groups()[:3]), n) for n in tags if (mm := rx.match(n))]
        if not cands:
            die(f"no tag matching {track.get('pattern')} on {url}")
        name = max(cands)[1]
        return name, tags[name]
    die(f"unknown track type {track['type']}")


# ---------- throwaway partial clone ----------

class Work:
    def __init__(self, url: str):
        self.dir = Path(tempfile.mkdtemp(prefix="wiki-src-"))
        git("init", "-q", cwd=self.dir)
        git("remote", "add", "origin", url, cwd=self.dir)
        git("config", "remote.origin.promisor", "true", cwd=self.dir)
        git("config", "remote.origin.partialclonefilter", "blob:none", cwd=self.dir)

    def fetch_commits(self, *shas: str) -> None:
        shas = tuple(s for s in shas if s and s != EMPTY_TREE)
        if shas:
            git("fetch", "-q", "--no-tags", "--depth=1", "--filter=blob:none", "origin", *shas, cwd=self.dir)

    def fetch_blobs(self, oids: list[str]) -> None:
        for i in range(0, len(oids), BATCH):
            git("fetch", "-q", "--no-tags", "--filter=blob:none", "origin", *oids[i:i + BATCH], cwd=self.dir)

    def changes(self, old: str, new: str, paths: list[str]) -> list[dict]:
        out = git("diff", "--no-renames", "--raw", "--no-abbrev", "-z", old, new, "--", *paths, cwd=self.dir)
        parts = out.split("\0")
        res = []
        i = 0
        while i < len(parts) - 1:
            meta, path = parts[i], parts[i + 1]
            i += 2
            f = meta.lstrip(":").split()
            mode_new, oid_new, status = f[1], f[3], f[4]
            if mode_new == "160000":  # submodule pointer, nothing to mirror
                continue
            res.append({"status": status[0], "path": path, "oid": oid_new})
        return res

    def tree_blobs(self, rev: str, paths: list[str]) -> dict[str, str]:
        out = git("ls-tree", "-r", "-z", rev, "--", *paths, cwd=self.dir)
        res = {}
        for entry in out.split("\0"):
            if not entry:
                continue
            meta, path = entry.split("\t", 1)
            mode, typ, oid = meta.split()
            if typ == "blob":
                res[path] = oid
        return res

    def blob(self, oid: str) -> bytes:
        return subprocess.run(["git", "cat-file", "blob", oid], cwd=self.dir,
                              capture_output=True, check=True).stdout

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def prune_empty_dirs(start: Path, stop: Path) -> None:
    d = start
    while d != stop and d.is_dir() and not any(d.iterdir()):
        d.rmdir()
        d = d.parent


# ---------- commands ----------

def cmd_check(a) -> None:
    m = load()
    ids = a.ids or [s["id"] for s in m["sources"]]
    rows = []
    for sid in ids:
        s = find(m, sid)
        ref, sha = resolve_remote(s)
        rows.append({"id": sid, "ingested_ref": s.get("ref"), "ingested_commit": s.get("commit"),
                     "upstream_ref": ref, "upstream_commit": sha,
                     "up_to_date": sha == s.get("commit")})
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    for r in rows:
        state = "up to date" if r["up_to_date"] else f"NEW: {r['ingested_ref']} -> {r['upstream_ref']}"
        print(f"{r['id']:<40} {(r['upstream_commit'] or '')[:12]}  {state}")


def plan(s: dict, to: str | None) -> tuple[Work, str, str, list[dict]]:
    ref, new = resolve_remote(s, to)
    old = s.get("commit") or EMPTY_TREE
    w = Work(s["url"])
    w.fetch_commits(old, new)
    if old == EMPTY_TREE:
        ch = [{"status": "A", "path": p, "oid": o} for p, o in w.tree_blobs(new, s["paths"]).items()]
    else:
        ch = w.changes(old, new, s["paths"])
    return w, ref, new, ch


def cmd_diff(a) -> None:
    s = find(load(), a.id)
    w, ref, new, ch = plan(s, a.to)
    try:
        print(f"{a.id}: {s.get('ref')} ({(s.get('commit') or 'none')[:12]}) -> {ref} ({new[:12]})")
        for c in ch:
            print(f"  {c['status']}  {c['path']}")
        print(f"{len(ch)} file(s) changed under tracked paths")
    finally:
        w.close()


def apply(s: dict, w: Work, ch: list[dict], dry: bool) -> None:
    raw = ROOT / s["raw_dir"]
    need = sorted({c["oid"] for c in ch if c["status"] in "AMT"})
    if not dry and need:
        w.fetch_blobs(need)
    for c in ch:
        dest = raw / c["path"]
        if dry:
            continue
        if c["status"] == "D":
            if dest.exists():
                dest.unlink()
                prune_empty_dirs(dest.parent, raw)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(w.blob(c["oid"]))


def cmd_sync(a, initial: bool = False) -> None:
    m = load()
    s = find(m, a.id)
    w, ref, new, ch = plan(s, getattr(a, "to", None))
    try:
        if new == s.get("commit") and not initial:
            print(json.dumps({"id": a.id, "ref": ref, "commit": new, "changed": []}, indent=2))
            return
        apply(s, w, ch, a.dry_run)
    finally:
        w.close()
    report = {"id": a.id, "from_ref": s.get("ref"), "from_commit": s.get("commit"),
              "ref": ref, "commit": new, "dry_run": a.dry_run,
              "raw_dir": s["raw_dir"], "source_pages": s.get("source_pages", []),
              "changed": [{"status": c["status"], "path": c["path"]} for c in ch]}
    if not a.dry_run:
        hist = s.setdefault("history", [])
        if s.get("commit"):
            hist.append({"ref": s.get("ref"), "commit": s["commit"], "synced": s.get("synced")})
        s.update({"ref": ref, "commit": new, "synced": today()})
        save(m)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def cmd_add(a) -> None:
    m = load()
    if any(s["id"] == a.id for s in m["sources"]):
        die(f"source '{a.id}' already exists")
    if bool(a.branch) == bool(a.tag_pattern):
        die("pass exactly one of --branch or --tag-pattern")
    track = ({"type": "branch", "name": a.branch} if a.branch else
             {"type": "tag", "pattern": a.tag_pattern, "include_prereleases": a.include_prereleases})
    m["sources"].append({"id": a.id, "url": a.url, "track": track, "paths": a.path,
                         "raw_dir": a.raw_dir, "source_pages": a.source_page or [],
                         "ref": None, "commit": None, "synced": None})
    save(m)
    a.dry_run = False
    cmd_sync(a, initial=True)


def cmd_verify(a) -> None:
    s = find(load(), a.id)
    w = Work(s["url"])
    try:
        w.fetch_commits(s["commit"])
        tree = w.tree_blobs(s["commit"], s["paths"])
    finally:
        w.close()
    raw = ROOT / s["raw_dir"]
    local = {}
    for p in s["paths"]:
        base = raw / p
        files = [base] if base.is_file() else [f for f in base.rglob("*") if f.is_file()] if base.is_dir() else []
        for f in files:
            local[str(f.relative_to(raw))] = None
    if local:
        rels = sorted(local)
        out = git("hash-object", "--no-filters", "--stdin-paths", cwd=raw,
                  input="\n".join(str(raw / r) for r in rels) + "\n")
        local = dict(zip(rels, out.split()))
    missing = sorted(set(tree) - set(local))
    extra = sorted(set(local) - set(tree))
    differ = sorted(p for p in set(tree) & set(local) if tree[p] != local[p])
    print(f"{a.id} @ {s.get('ref')} ({s['commit'][:12]}): {len(tree)} upstream files, "
          f"{len(missing)} missing, {len(extra)} extra, {len(differ)} different")
    for tag, lst in (("missing", missing), ("extra", extra), ("differs", differ)):
        for p in lst:
            print(f"  {tag}: {p}")
    sys.exit(1 if (missing or extra or differ) else 0)


def resolve_root(root: str | None, manifest: str | None) -> None:
    global ROOT, MANIFEST
    if root or os.environ.get("WIKI_SOURCES_ROOT"):
        ROOT = Path(root or os.environ["WIKI_SOURCES_ROOT"]).expanduser().resolve()
    else:
        here = Path.cwd().resolve()
        found = next((d for d in (here, *here.parents) if (d / "raw" / "sources.json").is_file()), None)
        if found is None:
            r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
            found = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else here
        ROOT = found
    m = manifest or os.environ.get("WIKI_SOURCES_MANIFEST")
    MANIFEST = Path(m).expanduser().resolve() if m else ROOT / "raw" / "sources.json"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="wiki project root (see Root resolution)")
    p.add_argument("--manifest", help="path to sources.json (default <root>/raw/sources.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("ids", nargs="*"); c.add_argument("--json", action="store_true")
    d = sub.add_parser("diff"); d.add_argument("id"); d.add_argument("--to")
    s = sub.add_parser("sync"); s.add_argument("id"); s.add_argument("--to"); s.add_argument("--dry-run", action="store_true")
    ad = sub.add_parser("add")
    ad.add_argument("id"); ad.add_argument("url"); ad.add_argument("--raw-dir", required=True)
    ad.add_argument("--path", action="append", required=True)
    ad.add_argument("--branch"); ad.add_argument("--tag-pattern")
    ad.add_argument("--include-prereleases", action="store_true")
    ad.add_argument("--source-page", action="append")
    v = sub.add_parser("verify"); v.add_argument("id")
    a = p.parse_args()
    resolve_root(a.root, a.manifest)
    {"check": cmd_check, "diff": cmd_diff, "sync": cmd_sync, "add": cmd_add, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    main()

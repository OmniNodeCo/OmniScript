#!/usr/bin/env python3
"""Turn a directory of release files into a fake GitHub API, for a rehearsal.

    python3 tools/make_release_fixture.py --dist dist --out /tmp/release
    ./install.sh --channel release --api-url file:///tmp/release
    /tmp/release/... then behaves exactly like api.github.com

Copying what a release will contain into the layout the API uses -- and pointing
the installers and `omni update` at it with `file://` -- means the whole download
path can be rehearsed before a tag is ever pushed: asset choice for this
machine, the SHA256SUMS.txt check, the swap, the version it reports afterwards.

The fixture is also what the tests and CI serve over localhost, so a release that
works here works there.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from omniscript import __version__  # noqa: E402
from omniscript.update import DEFAULT_REPO, sha256_of, write_checksums  # noqa: E402


def build(dist: str, out: str, repo: str, version: str, base: str,
          checksums: bool = True) -> str:
    """Lay out `dist` as a release under `out`; returns the API root to use."""
    dist = os.path.abspath(dist)
    out = os.path.abspath(out)
    assets = os.path.join(out, "assets")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(assets)

    names = sorted(name for name in os.listdir(dist)
                   if os.path.isfile(os.path.join(dist, name))
                   and name != "SHA256SUMS.txt")
    if not names:
        raise SystemExit(f"make_release_fixture.py: no files to publish in {dist}")
    for name in names:
        shutil.copy2(os.path.join(dist, name), os.path.join(assets, name))
    if checksums:
        write_checksums(assets)
        names.append("SHA256SUMS.txt")

    api = base or "file://" + out
    listing = [{"name": name,
                "size": os.path.getsize(os.path.join(assets, name)),
                "browser_download_url": f"{api}/assets/{name}"}
               for name in sorted(names)]
    release = {
        "tag_name": f"v{version}",
        "name": f"OmniScript {version}",
        "body": "A rehearsal of a release, made by tools/make_release_fixture.py.",
        "published_at": "2026-01-01T00:00:00Z",
        "prerelease": False,
        "draft": False,
        "assets": listing,
    }
    releases = os.path.join(out, "repos", repo, "releases")
    os.makedirs(os.path.join(releases, "tags"), exist_ok=True)
    for relative in ("latest", os.path.join("tags", f"v{version}")):
        with open(os.path.join(releases, relative), "w", encoding="utf-8") as fh:
            json.dump(release, fh, indent=2)
            fh.write("\n")
    return api


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dist", required=True, help="the directory of files to publish")
    p.add_argument("--out", required=True, help="where to lay out the fake API")
    p.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/name   [{DEFAULT_REPO}]")
    p.add_argument("--version", default=__version__, help=f"tag to publish   [{__version__}]")
    p.add_argument("--base-url", default="",
                   help="URL prefix for the assets [file://OUT]")
    p.add_argument("--no-checksums", action="store_true",
                   help="leave SHA256SUMS.txt out, to rehearse an unchecked release")
    args = p.parse_args(argv)

    api = build(args.dist, args.out, args.repo, args.version, args.base_url,
                checksums=not args.no_checksums)
    files = sorted(os.listdir(os.path.join(args.out, "assets")))
    print(f"release v{args.version} of {args.repo} is laid out in {args.out}")
    for name in files:
        size = os.path.getsize(os.path.join(args.out, "assets", name))
        print(f"    {name}  {size:,} bytes  sha256 {sha256_of(os.path.join(args.out, 'assets', name))[:16]}...")
    print()
    print("rehearse it with:")
    print(f"    ./install.sh --channel release --api-url {api} --prefix /tmp/omni-rehearsal")
    print(f"    ./install.ps1 -Channel release -ApiUrl {api} -Prefix C:\\Temp\\omni-rehearsal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

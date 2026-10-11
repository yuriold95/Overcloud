"""HEAD/GET-check every external documentation URL used in mission templates and docs
(DECISIONS.md V-07). Usage: python scripts/check_links.py [--docs]"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

from overclouded.domain.mission_templates import TEMPLATES

ROOT = Path(__file__).resolve().parents[1]
URL = re.compile(r"https://[^\s)>\]\"'`]+")


def collect(include_docs: bool) -> set[str]:
    urls = {g.url for t in TEMPLATES.values() for g in t.guidance}
    if include_docs:
        for md in (ROOT / "docs").glob("*.md"):
            urls |= {u.rstrip(".,") for u in URL.findall(md.read_text())}
    return {u for u in urls if "example" not in u and "<" not in u and "{" not in u}


def main(argv: list[str]) -> int:
    bad = 0
    with httpx.Client(
        follow_redirects=True, timeout=20, headers={"User-Agent": "overclouded-linkcheck"}
    ) as client:
        for url in sorted(collect("--docs" in argv)):
            try:
                status = client.get(url).status_code
            except httpx.HTTPError as exc:
                status = 0
                print(f"ERR  {url} ({exc.__class__.__name__})")
            ok = 200 <= status < 400
            bad += 0 if ok else 1
            print(f"{'OK ' if ok else 'BAD'} {status} {url}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""CLI: python scripts/policy_lint.py <template-or-policy> [...] — exits 1 on any finding."""

from __future__ import annotations

import sys
from pathlib import Path

from overclouded.policy_lint import lint_file


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: policy_lint.py FILE [FILE ...]", file=sys.stderr)
        return 2
    failed = False
    for name in argv:
        errors = lint_file(Path(name))
        for err in errors:
            print(f"{name}: {err}", file=sys.stderr)
        failed = failed or bool(errors)
        if not errors:
            print(f"{name}: OK (read-only, ExternalId required)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

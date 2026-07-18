"""Command-line validation for trusted workbook-migration skills."""

from __future__ import annotations

import argparse
from pathlib import Path

from .skills import lint_skill_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path("agent/skills/xlsliberator")],
    )
    args = parser.parse_args()
    errors = [error for root in args.roots for error in lint_skill_root(root)]
    for error in errors:
        print(error)
    if errors:
        print(f"skill lint failed with {len(errors)} error(s)")
        return 1
    print(f"skill lint passed for {len(args.roots)} root(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

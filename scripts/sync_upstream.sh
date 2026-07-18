#!/usr/bin/env bash
set -euo pipefail

current_branch="$(git branch --show-current)"

if [[ -z "${current_branch}" || "${current_branch}" == "main" ]]; then
  echo "Run this script from a dedicated upstream-sync branch." >&2
  exit 2
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "The worktree must be clean before an upstream rebase." >&2
  exit 2
fi

git fetch --prune origin
git fetch --no-tags upstream main
git rebase upstream/main
scripts/check_upstream_drift.sh

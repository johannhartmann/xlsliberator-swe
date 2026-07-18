#!/usr/bin/env bash
set -euo pipefail

upstream_url="${OPEN_SWE_UPSTREAM_URL:-https://github.com/langchain-ai/open-swe.git}"
upstream_branch="${OPEN_SWE_UPSTREAM_BRANCH:-main}"

if git remote get-url upstream >/dev/null 2>&1; then
  git remote set-url upstream "${upstream_url}"
else
  git remote add upstream "${upstream_url}"
fi

git fetch --no-tags upstream "${upstream_branch}"
read -r fork_only upstream_only < <(
  git rev-list --left-right --count "HEAD...upstream/${upstream_branch}"
)

report="Open SWE drift: fork-only=${fork_only}, upstream-only=${upstream_only}"
echo "${report}"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "## Open SWE upstream drift"
    echo
    echo "- Fork-only commits: \`${fork_only}\`"
    echo "- Upstream-only commits: \`${upstream_only}\`"
    echo "- Upstream: \`${upstream_url}#${upstream_branch}\`"
  } >>"${GITHUB_STEP_SUMMARY}"
fi

if [[ "${upstream_only}" -gt 0 ]]; then
  echo "::warning::${report}; follow UPSTREAM_SYNC.md"
fi

if [[ "${STRICT_UPSTREAM_DRIFT:-0}" == "1" && "${upstream_only}" -gt 0 ]]; then
  exit 1
fi

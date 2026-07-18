# Synchronizing with Open SWE upstream

The fork retains Open SWE history and keeps domain changes under
`agent/xlsliberator/` wherever possible. Synchronization is performed through a
reviewed branch so upstream conflicts and behavior changes receive normal CI
and review.

## One-time remote setup

```bash
git remote add upstream https://github.com/langchain-ai/open-swe.git
git remote set-url --push upstream DISABLED
git remote -v
```

`origin` must point to `johannhartmann/xlsliberator-swe`; `upstream` is
fetch-only.

## Prepare a sync pull request

Start from a clean worktree:

```bash
git fetch --prune origin
git switch main
git pull --ff-only origin main
git switch -c chore/upstream-sync-YYYY-MM-DD
scripts/sync_upstream.sh
git push -u origin chore/upstream-sync-YYYY-MM-DD
gh pr create --base main --title "chore: sync Open SWE upstream"
```

The script fetches `upstream/main`, rebases the current sync branch, and reports
fork-only and upstream-only commits. It refuses to run on `main` or in a dirty
worktree. Resolve conflicts in the smallest possible assembly surface; do not
discard XLSLiberator domain changes.

After CI is green and the sync PR is merged, update
[UPSTREAM_OPEN_SWE.md](UPSTREAM_OPEN_SWE.md) with the synchronized upstream
commit. Run the complete Agent CI suite and verify the dashboard/API coding
task E2E before merging.

## Recovery

If an upstream change cannot be integrated without changing behavior, abort the
rebase with `git rebase --abort`, document the conflict in the implementation
ledger, and open a focused compatibility change. Never force-push `main`.

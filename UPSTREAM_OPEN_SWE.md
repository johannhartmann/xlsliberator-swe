# Open SWE upstream baseline

This repository is a thin fork of
[`langchain-ai/open-swe`](https://github.com/langchain-ai/open-swe). Its full
Git history is retained.

| Item | Value |
|---|---|
| Initial upstream branch | `langchain-ai/open-swe:main` |
| Initial upstream commit | `f0897479c38f2506f03b4de38081d4770928f09d` |
| Commit date | 2026-07-17 |
| Initial subject | `feat: surface context window usage in agents UI (#1778)` |
| Fork repository | `johannhartmann/xlsliberator-swe` |

The expected local remotes are:

```text
origin    git@github.com:johannhartmann/xlsliberator-swe.git
upstream  https://github.com/langchain-ai/open-swe.git
```

Run `scripts/check_upstream_drift.sh` to verify the current relationship. Use
the reviewed procedure in [UPSTREAM_SYNC.md](UPSTREAM_SYNC.md) to synchronize;
never replace the fork with a history-free copy.

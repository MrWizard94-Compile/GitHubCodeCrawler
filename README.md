# GitHub Code Crawler (WPAI)

Crawl **useful open-source code bits** from GitHub using the **official REST API** — not HTML scraping.

## Why API (not a web crawler)

| HTML scrape | GitHub API |
|-------------|------------|
| Violates ToS, gets blocked | Supported, token-scoped |
| Brittle markup | Stable JSON |
| Hard to filter license | `license` / SPDX fields |
| No structured rate limits | `X-RateLimit-*` headers |

## Features

- Code search: `GET /search/code` (authenticated)
- Repo star filters, language, path, filename
- **License allow-list** (MIT, Apache-2.0, BSD, …) by default
- **Secret heuristics** drop PATs, AWS keys, private keys, etc.
- Append-only **JSONL** store with provenance (repo, path, URL, license)
- Auth via `GITHUB_TOKEN` / `GH_TOKEN` / `gh auth token`

## Setup

```powershell
cd C:\WPAI\Software\GitHubCodeCrawler
pip install -r requirements.txt

# Token (pick one)
# 1) Already logged in:
gh auth status
# 2) Or:
$env:GITHUB_TOKEN = "ghp_..."   # classic PAT needs `public_repo` or fine-grained Contents:Read + Metadata
```

**Scopes:** for public code search + file contents, a classic PAT with `public_repo` (or fine-grained: Repository Contents Read on public repos) is enough.

## Usage

```powershell
# FIRST MISSION: code for WPAI improve-swarm / self-improvement
python -m github_code_crawler mission --profile self-improvement --max-pages 1 --per-page 8
# → out/self-improvement/snippets.jsonl + FINDINGS.md
# → StudioOps/improve-swarm/GITHUB-CRAWL-SELF-IMPROVEMENT.md

python -m github_code_crawler profiles

# Ad-hoc search
python -m github_code_crawler search "exponential backoff" --language python --min-stars 200 --max-pages 1

# Raw GitHub query syntax
python -m github_code_crawler search "filename:Dockerfile stars:>=500" --raw-query --max-pages 1

# Stats / show kept snippets
python -m github_code_crawler stats --out out/self-improvement/snippets.jsonl
python -m github_code_crawler show --out out/self-improvement/snippets.jsonl --limit 3 --max-chars 800
```

Output default: `out/snippets.jsonl`

## Legal / ethical (non-negotiable)

1. **License is not optional.** Default denies GPL/AGPL/unknown. Only keep what you will comply with.
2. **Attribution:** every kept row has `repo_full_name`, `html_url`, `license_spdx`.
3. **Secrets:** never keep bodies that match secret patterns; metadata-only drop records are allowed.
4. **Rate limits:** code search is ~**10 requests/minute** authenticated — the client sleeps between pages.
5. **Do not** treat crawled code as public domain or paste it into commercial products without license review.

## Self-improvement mission (default first use)

Maps GitHub searches onto **WPAI improve-swarm** concepts:

| Spec | Maps to |
|------|---------|
| tournament-selection | diverse survivors |
| nsga-diversity | score plateau / multi-objective |
| elitism-hall-of-fame | `elite.json` |
| gene-mutation | `Invoke-WpaiImproveMutate` |
| bandit-explore | fitness `explore_bonus` |
| experiment-tracking | `outcomes.jsonl` |
| self-play-loop | unleash / auto-review |
| property-test | falsify probes |
| retry-backoff | reliable auto-experiments |
| fitness-landscape | `Get-WpaiImproveFitness` |

**Note:** `stars:` in GitHub *code* search often returns zero hits; star filtering is client-side / optional.

## What this is *not*

- Not a bulk mirror of GitHub
- Not training-data scrape at internet scale
- Not a substitute for reading upstream docs and LICENSE files

## Tests (offline)

```powershell
python tests\test_filters.py
```

## WPAI integration notes

- Useful for StudioOps / Janus research: find battle-tested algorithms (retry, rate limit, packing).
- Pair with HITL: never auto-merge crawled code into product repos without review.
- Store stays local under `out/` (gitignored recommended for large dumps).

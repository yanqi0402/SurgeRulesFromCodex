# SurgeRulesFromCodex

Auto-maintained Surge rule lists.

## Files

- `AI.list`: AI-related domains for Surge `RULE-SET` usage
- `scripts/update_ai_rules.py`: fetches official sources and regenerates `AI.list`
- `.github/workflows/update-ai-rules.yml`: runs the updater on schedule and pushes changes

## Current coverage

`AI.list` currently tracks Claude Code's official network access requirements from:

- `https://code.claude.com/docs/en/network-config`
- `https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps`

The updater is intentionally structured so we can add more AI services later without replacing the existing file layout.

For OpenAI, the rules are kept as a curated official baseline because the Help Center currently uses Cloudflare bot challenges that block unattended fetches in simple CI clients.

## Automation

The GitHub Actions workflow runs every day at 09:15 Asia/Shanghai time, which is `01:15 UTC`, and can also be triggered manually from the Actions tab.

When the upstream domains change, the workflow regenerates `AI.list` and commits the update back to `main`.

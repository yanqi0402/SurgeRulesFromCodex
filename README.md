# SurgeRulesFromCodex

Auto-maintained Surge rule lists.

## Files

- `AI.list`: AI-related domains, currently including Claude Code, OpenAI, and Apple Intelligence
- `apple.list`: Apple service domains
- `netflix.list`: Netflix domains
- `hbo_max.list`: Max / HBO Max domains
- `tik_tok.list`: TikTok international domains
- `microsoft.list`: Microsoft domains
- `scripts/update_ai_rules.py`: regenerates all rule list files
- `.github/workflows/update-ai-rules.yml`: runs the updater on schedule and pushes changes

## Current coverage

`AI.list` currently tracks:

- `https://code.claude.com/docs/en/network-config`
- `https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps`
- `https://support.apple.com/en-us/101555`

Additional list files currently track:

- Apple services in `apple.list`
- Netflix in `netflix.list`
- Max / HBO Max in `hbo_max.list`
- TikTok international in `tik_tok.list`
- Microsoft in `microsoft.list`

The updater is intentionally structured so we can add more services later without replacing the existing file layout.

For OpenAI, Netflix, Max / HBO Max, and TikTok, the repo currently keeps curated baselines. OpenAI's Help Center uses Cloudflare bot challenges that block simple unattended fetches, while Netflix and Max don't publish a practical public allowlist we can scrape reliably. The TikTok list is intentionally conservative and sticks to the official TikTok host families visible in developer documentation. Microsoft is generated from the official Microsoft 365 endpoint web service when available, with a curated fallback baseline.

## Automation

The GitHub Actions workflow runs every day at 09:15 Asia/Shanghai time, which is `01:15 UTC`, and can also be triggered manually from the Actions tab.

When the upstream domains or curated baselines change, the workflow regenerates all list files and commits the update back to `main`.

# SurgeRulesFromCodex

Auto-maintained Surge rule lists.

## Files

- `AI.list`: AI-related domains, currently including Claude, Claude Code, OpenAI, Sora, Apple Intelligence, Copilot, Google AI services, Grok, Groq, Cursor, Perplexity, Windsurf, Zed, and more
- `apple.list`: Apple service domains
- `netflix.list`: Netflix domains
- `hbo_max.list`: Max / HBO Max domains
- `tik_tok.list`: TikTok international domains
- `microsoft.list`: Microsoft domains
- `scripts/update_ai_rules.py`: regenerates all rule list files
- `.github/workflows/update-ai-rules.yml`: runs the updater on schedule and pushes changes

## Current coverage

`AI.list` currently tracks a mix of live-fetched official sources and curated first-party baselines for commonly blocked international AI services.

Live-fetched sources currently include:

- `https://code.claude.com/docs/en/network-config`

Curated official or first-party baselines currently include services such as:

- Claude / Claude Code
- OpenAI / Sora
- Apple Intelligence / Siri
- Google AI Studio / Gemini / NotebookLM / Gemini API / DeepMind
- Microsoft Copilot / GitHub Copilot
- Grok / Groq / Cursor / Dify / OpenRouter / Perplexity / Poe / Windsurf / Zed

Additional list files currently track:

- Apple services in `apple.list`
- Netflix in `netflix.list`
- Max / HBO Max in `hbo_max.list`
- TikTok international in `tik_tok.list`
- Microsoft in `microsoft.list`

The updater is intentionally structured so we can add more services later without replacing the existing file layout.

For most AI services, the repo intentionally keeps conservative first-party baselines because vendors rarely publish a clean public allowlist. OpenAI's Help Center uses Cloudflare bot challenges that block simple unattended fetches, while many other AI vendors publish product domains but not formal network requirement tables. Microsoft is generated from the official Microsoft 365 endpoint web service when available, with a curated fallback baseline.

## Automation

The GitHub Actions workflow runs every day at 09:15 Asia/Shanghai time, which is `01:15 UTC`, and can also be triggered manually from the Actions tab.

When the upstream domains or curated baselines change, the workflow regenerates all list files and commits the update back to `main`.

For local scheduled runs outside GitHub Actions, `scripts/run_local_update_and_commit.py` refreshes both the parent Claude Code outputs and this repo's rule lists, then creates a commit only when:

- the subrepo is clean before the run
- only the publishable rule list files changed

This keeps unattended local automation from accidentally committing unrelated manual edits.

#!/usr/bin/env python3
"""Update AI-related Surge rule lists from official sources."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

OUTPUT_PATH = Path("AI.list")

HOSTNAME_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)
LIST_ITEM_RE = re.compile(
    r"<li[^>]*>.*?<code[^>]*>(?P<domain>[a-z0-9.-]+\.[a-z]{2,})</code>"
    r"(?P<rest>.*?)</li>",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class RuleEntry:
    rule_type: str
    value: str


@dataclass(frozen=True)
class Provider:
    name: str
    source_url: str
    intro_markers: tuple[str, ...] = ()
    fallback_rules: tuple[RuleEntry, ...] = ()
    match_roots: tuple[str, ...] = ()
    exact_allow: tuple[str, ...] = ()
    live_fetch: bool = True
    note: str = ""


def domain(value: str) -> RuleEntry:
    return RuleEntry("DOMAIN", value)


def domain_suffix(value: str) -> RuleEntry:
    return RuleEntry("DOMAIN-SUFFIX", value)


CLAUDE_CODE = Provider(
    name="Claude Code",
    source_url="https://code.claude.com/docs/en/network-config",
    intro_markers=(
        "Claude Code requires access to the following URLs:",
        "The native installer and update checks also require the following URLs.",
    ),
    fallback_rules=(
        domain("api.anthropic.com"),
        domain("claude.ai"),
        domain("downloads.claude.ai"),
        domain("platform.claude.com"),
        domain("storage.googleapis.com"),
    ),
    match_roots=("anthropic.com", "claude.ai", "claude.com"),
    exact_allow=("storage.googleapis.com",),
)

OPENAI = Provider(
    name="OpenAI",
    source_url="https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps",
    fallback_rules=(
        domain_suffix("chatgpt.com"),
        domain_suffix("ct.sendgrid.net"),
        domain_suffix("featuregates.org"),
        domain_suffix("intercom.io"),
        domain_suffix("intercomcdn.com"),
        domain_suffix("oaistatic.com"),
        domain_suffix("oaiusercontent.com"),
        domain_suffix("openai.com"),
        domain_suffix("statsig.com"),
        domain("cdn.openaimerge.com"),
        domain("cdn.workos.com"),
        domain("challenges.cloudflare.com"),
        domain("events.statsigapi.net"),
        domain("featureassets.org"),
        domain("forwarder.workos.com"),
        domain("humb.apple.com"),
        domain("images.workoscdn.com"),
        domain("js.stripe.com"),
        domain("o207216.ingest.sentry.io"),
        domain("o33249.ingest.sentry.io"),
        domain("prodregistryv2.org"),
        domain("rum.browser-intake-datadoghq.com"),
        domain("setup.workos.com"),
        domain("statsigapi.net"),
        domain("workos.imgix.net"),
    ),
    live_fetch=False,
    note=(
        "Curated from OpenAI's official allowlist article. The Help Center is currently "
        "protected by Cloudflare challenges, so the updater keeps this official baseline "
        "instead of attempting unattended scraping."
    ),
)

PROVIDERS = (CLAUDE_CODE, OPENAI)


def fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


def sanitize_text(text: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def looks_relevant(domain: str, provider: Provider) -> bool:
    domain = domain.lower()
    if domain in provider.exact_allow:
        return True
    return any(domain == root or domain.endswith(f".{root}") for root in provider.match_roots)


def extract_lists_by_intro(html_text: str, markers: Iterable[str]) -> list[str]:
    fragments: list[str] = []
    for marker in markers:
        position = html_text.find(marker)
        if position == -1:
            continue
        match = re.search(r"<ul[^>]*>.*?</ul>", html_text[position:], re.IGNORECASE | re.DOTALL)
        if match:
            fragments.append(match.group(0))
    return fragments


def extract_rules(provider: Provider, html_text: str) -> list[RuleEntry]:
    rules: set[RuleEntry] = set()
    for fragment in extract_lists_by_intro(html_text, provider.intro_markers):
        for match in LIST_ITEM_RE.finditer(fragment):
            domain = match.group("domain").lower()
            if looks_relevant(domain, provider):
                rules.add(domain_rule(domain))

    if rules:
        return sort_rules(rules)

    for domain in HOSTNAME_RE.findall(sanitize_text(html_text)):
        domain = domain.lower()
        if looks_relevant(domain, provider):
            rules.add(domain_rule(domain))
    return sort_rules(rules)


def domain_rule(domain_name: str) -> RuleEntry:
    return domain(domain_name)


def sort_rules(rules: Iterable[RuleEntry]) -> list[RuleEntry]:
    return sorted(rules, key=lambda rule: (rule.rule_type, rule.value))


def resolve_provider_rules(provider: Provider) -> list[RuleEntry]:
    if not provider.live_fetch:
        return sort_rules(provider.fallback_rules)

    try:
        html_text = fetch_html(provider.source_url)
    except URLError as exc:
        print(
            f"[warn] {provider.name}: failed to fetch official source, using fallback ({exc})",
            file=sys.stderr,
        )
        return sort_rules(provider.fallback_rules)

    rules = extract_rules(provider, html_text)
    if rules:
        return rules

    print(
        f"[warn] {provider.name}: failed to parse official source, using fallback",
        file=sys.stderr,
    )
    return sort_rules(provider.fallback_rules)


def render_rules() -> str:
    lines = [
        "# Auto-generated by scripts/update_ai_rules.py.",
        "# Intended for Surge RULE-SET usage.",
        "",
    ]

    for provider in PROVIDERS:
        rules = resolve_provider_rules(provider)
        lines.append(f"# {provider.name}")
        lines.append(f"# Source: {provider.source_url}")
        if provider.note:
            lines.append(f"# Note: {provider.note}")
        for rule in rules:
            lines.append(f"{rule.rule_type},{rule.value}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    OUTPUT_PATH.write_text(render_rules(), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

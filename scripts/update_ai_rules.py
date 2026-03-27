#!/usr/bin/env python3
"""Update curated Surge rule lists from official and curated sources."""

from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

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
    source_kind: str = "html_list"


@dataclass(frozen=True)
class RuleList:
    output_path: Path
    providers: tuple[Provider, ...]


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

APPLE_INTELLIGENCE = Provider(
    name="Apple Intelligence",
    source_url="https://support.apple.com/en-us/101555",
    fallback_rules=(
        domain("apple-relay.apple.com"),
        domain("apple-relay.cloudflare.com"),
        domain("apple-relay.fastly-edge.com"),
        domain("cp4.cloudflare.com"),
        domain("guzzoni.apple.com"),
        domain_suffix("smoot.apple.com"),
    ),
    live_fetch=False,
    note=(
        "Curated from Apple's enterprise network guidance for Apple Intelligence, Siri, "
        "and Search."
    ),
)

APPLE_SERVICES = Provider(
    name="Apple Services",
    source_url="https://support.apple.com/en-us/101555",
    fallback_rules=(
        domain_suffix("apple.com"),
        domain_suffix("apple-cloudkit.com"),
        domain_suffix("cdn-apple.com"),
        domain_suffix("icloud.com"),
        domain_suffix("icloud-content.com"),
        domain_suffix("icloud.com.cn"),
        domain_suffix("mzstatic.com"),
        domain_suffix("networking.apple"),
    ),
    live_fetch=False,
    note=(
        "Broad Apple services baseline distilled from Apple's enterprise host tables. "
        "It favors practical Surge suffix rules over a verbatim per-host translation."
    ),
)

NETFLIX = Provider(
    name="Netflix",
    source_url="https://www.netflix.com",
    fallback_rules=(
        domain_suffix("fast.com"),
        domain_suffix("netflix.com"),
        domain_suffix("nflxext.com"),
        domain_suffix("nflximg.net"),
        domain_suffix("nflxso.net"),
        domain_suffix("nflxvideo.net"),
    ),
    live_fetch=False,
    note=(
        "Netflix does not publish a public allowlist. This is a conservative first-party "
        "baseline inferred from stable Netflix-owned service and media domains."
    ),
)

HBO_MAX = Provider(
    name="HBO Max / Max",
    source_url="https://www.max.com",
    fallback_rules=(
        domain_suffix("hbomax.com"),
        domain_suffix("max.com"),
    ),
    live_fetch=False,
    note=(
        "Conservative first-party baseline for Max/HBO Max brand domains. Expand this "
        "section later if you want to capture additional service-specific delivery hosts."
    ),
)

TIKTOK_INTL = Provider(
    name="TikTok (International)",
    source_url="https://developers.tiktok.com/doc/content-posting-api-get-started/",
    fallback_rules=(
        domain_suffix("tiktok.com"),
        domain_suffix("tiktokapis.com"),
        domain_suffix("tiktokcdn.com"),
    ),
    live_fetch=False,
    note=(
        "Conservative international TikTok baseline built from official TikTok developer "
        "docs that explicitly show tiktok.com, open.tiktokapis.com, open-upload.tiktokapis.com, "
        "and tiktokcdn.com. Expand later if you want a broader inferred ByteDance CDN set."
    ),
)

MICROSOFT = Provider(
    name="Microsoft",
    source_url="https://endpoints.office.com/endpoints/worldwide",
    fallback_rules=(
        domain_suffix("live.com"),
        domain_suffix("microsoft.com"),
        domain_suffix("microsoftonline.com"),
        domain_suffix("microsoft365.com"),
        domain_suffix("msauth.net"),
        domain_suffix("msauthimages.net"),
        domain_suffix("msftauth.net"),
        domain_suffix("msftauthimages.net"),
        domain_suffix("office.com"),
        domain_suffix("office.net"),
        domain_suffix("office365.com"),
        domain_suffix("onedrive.com"),
        domain_suffix("onenote.net"),
        domain_suffix("onmicrosoft.com"),
        domain_suffix("outlook.com"),
        domain_suffix("sharepoint.com"),
        domain_suffix("skype.com"),
        domain_suffix("teams.microsoft.com"),
        domain_suffix("windows.net"),
    ),
    note=(
        "Generated from Microsoft's official Microsoft 365 endpoint web service when "
        "available, with a fallback baseline of core identity and productivity domains."
    ),
    source_kind="m365_endpoints",
)

RULE_LISTS = (
    RuleList(
        output_path=Path("AI.list"),
        providers=(CLAUDE_CODE, OPENAI, APPLE_INTELLIGENCE),
    ),
    RuleList(
        output_path=Path("apple.list"),
        providers=(APPLE_SERVICES,),
    ),
    RuleList(
        output_path=Path("netflix.list"),
        providers=(NETFLIX,),
    ),
    RuleList(
        output_path=Path("hbo_max.list"),
        providers=(HBO_MAX,),
    ),
    RuleList(
        output_path=Path("tik_tok.list"),
        providers=(TIKTOK_INTL,),
    ),
    RuleList(
        output_path=Path("microsoft.list"),
        providers=(MICROSOFT,),
    ),
)


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


def fetch_json(url: str) -> object:
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
    with urlopen(request, timeout=20) as response:
        return json.load(response)


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


def normalize_wildcard_url(raw_value: str) -> RuleEntry | None:
    value = raw_value.strip().lower()
    if not value:
        return None
    if value.startswith("*."):
        return domain_suffix(value[2:])
    if value.startswith("*"):
        return domain_suffix(value[1:].lstrip("."))
    if "*" in value:
        suffix = value.split("*")[-1].lstrip(".")
        return domain_suffix(suffix) if suffix else None
    return domain(value)


def sort_rules(rules: Iterable[RuleEntry]) -> list[RuleEntry]:
    return sorted(rules, key=lambda rule: (rule.rule_type, rule.value))


def extract_microsoft_rules(provider: Provider) -> list[RuleEntry]:
    client_request_id = uuid.uuid4()
    endpoint_url = f"{provider.source_url}?clientrequestid={client_request_id}"
    payload = fetch_json(endpoint_url)
    if not isinstance(payload, list):
        return []

    rules: set[RuleEntry] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        for raw_value in entry.get("urls") or []:
            if not isinstance(raw_value, str):
                continue
            rule = normalize_wildcard_url(raw_value)
            if rule is not None:
                rules.add(rule)

    return sort_rules(rules)


def resolve_provider_rules(provider: Provider) -> list[RuleEntry]:
    if not provider.live_fetch:
        return sort_rules(provider.fallback_rules)

    try:
        if provider.source_kind == "m365_endpoints":
            rules = extract_microsoft_rules(provider)
        else:
            html_text = fetch_html(provider.source_url)
            rules = extract_rules(provider, html_text)
    except (URLError, OSError, ValueError) as exc:
        print(
            f"[warn] {provider.name}: failed to fetch official source, using fallback ({exc})",
            file=sys.stderr,
        )
        return sort_rules(provider.fallback_rules)
    if rules:
        return rules

    print(
        f"[warn] {provider.name}: failed to parse official source, using fallback",
        file=sys.stderr,
    )
    return sort_rules(provider.fallback_rules)


def render_rules(rule_list: RuleList) -> str:
    lines = [
        "# Auto-generated by scripts/update_ai_rules.py.",
        "# Intended for Surge RULE-SET usage.",
        "",
    ]

    for provider in rule_list.providers:
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
    for rule_list in RULE_LISTS:
        rule_list.output_path.write_text(render_rules(rule_list), encoding="utf-8")
        print(f"Wrote {rule_list.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

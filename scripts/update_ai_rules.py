#!/usr/bin/env python3
"""Update curated Surge rule lists from official and curated sources."""

from __future__ import annotations

import json
import re
import sys
import textwrap
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
    method: str = ""
    process: str = ""
    note: str = ""
    source_kind: str = "html_list"


@dataclass(frozen=True)
class RuleList:
    output_path: Path
    providers: tuple[Provider, ...]


@dataclass(frozen=True)
class ProviderResult:
    provider: Provider
    rules: tuple[RuleEntry, ...]
    used_fallback: bool = False
    error: str | None = None


def domain(value: str) -> RuleEntry:
    return RuleEntry("DOMAIN", value)


def domain_suffix(value: str) -> RuleEntry:
    return RuleEntry("DOMAIN-SUFFIX", value)


def curated_provider(
    name: str,
    source_url: str,
    *,
    suffixes: tuple[str, ...] = (),
    domains: tuple[str, ...] = (),
    method: str = "Curated first-party baseline.",
    process: str,
    note: str = "",
) -> Provider:
    rules = tuple(domain(value) for value in domains) + tuple(
        domain_suffix(value) for value in suffixes
    )
    return Provider(
        name=name,
        source_url=source_url,
        fallback_rules=rules,
        live_fetch=False,
        method=method,
        process=process,
        note=note,
    )


CLAUDE = curated_provider(
    name="Claude",
    source_url="https://claude.ai/",
    suffixes=("anthropic.com", "claude.ai", "claudeusercontent.com"),
    method="Curated first-party baseline from Anthropic's public product domains.",
    process=(
        "Keep Anthropic-owned domains that directly front the Claude web app, shared content, "
        "and account-level traffic. This broader Claude block complements the narrower official "
        "Claude Code network allowlist."
    ),
    note="Covers general Claude app access in addition to the separate Claude Code block.",
)


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
    method="Live fetch from Anthropic's official Claude Code network configuration page.",
    process=(
        "Download the official documentation page, locate the documented URL lists for core "
        "access plus installer and update traffic, extract hostnames, convert them to Surge "
        "DOMAIN rules, and fall back to a small official baseline if fetching or parsing fails."
    ),
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
    method="Curated official baseline from OpenAI's allowlist guidance.",
    process=(
        "Start from OpenAI's official allowlist article, keep the clearly documented OpenAI "
        "and third-party dependency host families, map exact hosts to DOMAIN and broad "
        "families to DOMAIN-SUFFIX, and store the result statically because the Help Center "
        "blocks unattended scraping with Cloudflare challenges."
    ),
    note=(
        "Curated from OpenAI's official allowlist article. The Help Center is currently "
        "protected by Cloudflare challenges, so the updater keeps this official baseline "
        "instead of attempting unattended scraping."
    ),
)

SORA = curated_provider(
    name="Sora",
    source_url="https://sora.com/",
    suffixes=("sora.com",),
    domains=("sora-cdn.oaistatic.com",),
    method="Curated service-specific baseline from OpenAI's Sora product domains.",
    process=(
        "Keep the dedicated Sora web domain and the exact Sora-specific OpenAI static asset host "
        "so the service can be routed independently even though broader OpenAI domains already "
        "appear elsewhere in AI.list."
    ),
    note="The exact Sora CDN host is retained for clarity even though oaistatic.com is already covered by OpenAI.",
)

APPLE_INTELLIGENCE = Provider(
    name="Apple Intelligence",
    source_url="https://support.apple.com/en-us/101555",
    fallback_rules=(
        domain("apple-relay.apple.com"),
        domain("apple-relay.cloudflare.com"),
        domain("apple-relay.fastly-edge.com"),
        domain("cp4.cloudflare.com"),
        domain("gspe1-ssl.ls.apple.com"),
        domain("guzzoni.apple.com"),
        domain_suffix("smoot.apple.com"),
    ),
    live_fetch=False,
    method="Curated official baseline from Apple's enterprise network guidance.",
    process=(
        "Use Apple's published Apple Intelligence, Siri, and Search network guidance, keep the "
        "explicit Apple relay and assistant hosts needed by the feature set, and translate them "
        "into a compact mix of DOMAIN and DOMAIN-SUFFIX rules."
    ),
    note=(
        "Curated from Apple's enterprise network guidance for Apple Intelligence, Siri, and Search."
    ),
)

CEREBRAS = curated_provider(
    name="Cerebras",
    source_url="https://www.cerebras.ai/",
    suffixes=("cerebras.ai",),
    process=(
        "Use Cerebras' primary AI product domain as a focused DOMAIN-SUFFIX rule so hosted "
        "inference and console access can be proxied without introducing unrelated third-party hosts."
    ),
)

CHORUS = curated_provider(
    name="Chorus",
    source_url="https://chorus.sh/",
    suffixes=("chorus.sh",),
    process=(
        "Use Chorus' primary product domain as a compact first-party baseline and avoid expanding "
        "into undocumented infrastructure that the vendor does not publicly enumerate."
    ),
)

CLOUDFLARE_AI_GATEWAY = curated_provider(
    name="Cloudflare AI Gateway",
    source_url="https://developers.cloudflare.com/ai-gateway/",
    domains=("gateway.ai.cloudflare.com",),
    method="Curated official exact-host baseline from Cloudflare's AI Gateway documentation.",
    process=(
        "Keep Cloudflare AI Gateway on its documented entry hostname and express it as an exact "
        "DOMAIN rule because the product is fronted through a single stable gateway host."
    ),
)

MICROSOFT_COPILOT = curated_provider(
    name="Microsoft Copilot",
    source_url="https://copilot.microsoft.com/",
    domains=("copilot.microsoft.com",),
    suffixes=("microsoftonline.com",),
    method="Curated first-party baseline with Microsoft sign-in dependency.",
    process=(
        "Keep the dedicated Copilot web app hostname and the Microsoft account domain family "
        "commonly needed for sign-in and session establishment when AI.list is used without the "
        "broader microsoft.list ruleset."
    ),
    note="microsoftonline.com also appears in microsoft.list and is duplicated here for AI-only use.",
)

GITHUB_COPILOT = curated_provider(
    name="GitHub Copilot",
    source_url="https://github.com/features/copilot",
    domains=("api.github.com",),
    suffixes=("githubcopilot.com",),
    method="Curated AI-specific baseline with a GitHub API dependency.",
    process=(
        "Keep GitHub Copilot's dedicated service domain family plus the exact GitHub API host "
        "that is commonly used for Copilot token and service exchanges in editors and IDEs."
    ),
    note="api.github.com is broader than Copilot-only traffic, but it is commonly needed for Copilot auth and token flows.",
)

CURSOR = curated_provider(
    name="Cursor",
    source_url="https://cursor.sh/",
    suffixes=("cursor.sh",),
    process=(
        "Use Cursor's primary product domain as the first-party baseline for editor, auth, and "
        "update traffic that is visibly tied to the vendor-owned hostname."
    ),
)

DIA = curated_provider(
    name="DIA",
    source_url="https://www.diabrowser.engineering/",
    suffixes=("diabrowser.engineering",),
    process=(
        "Keep DIA's product domain family only, which is the most conservative way to proxy the "
        "service without assuming undocumented backend or CDN dependencies."
    ),
)

DIFY = curated_provider(
    name="Dify",
    source_url="https://dify.ai/",
    suffixes=("dify.ai",),
    process=(
        "Use Dify's primary hosted service domain as a focused baseline so the managed app and "
        "cloud entrypoints can be proxied without sweeping in unrelated generic infrastructure."
    ),
)

GOOGLE_AI_STUDIO = curated_provider(
    name="Google AI Studio",
    source_url="https://ai.google.dev/aistudio",
    domains=(
        "ai.google.dev",
        "alkalicore-pa.clients6.google.com",
        "alkalimakersuite-pa.clients6.google.com",
        "waa-pa.clients6.google.com",
    ),
    suffixes=("aistudio.google.com", "generativeai.google", "makersuite.google.com"),
    method="Curated official baseline from Google's Gemini developer and AI Studio properties.",
    process=(
        "Combine the current Google AI Studio entrypoints with the older MakerSuite compatibility "
        "domain and the exact Google bootstrap hosts that show up around studio initialization and "
        "developer console access."
    ),
    note="Retains both current and legacy Google AI Studio naming so older MakerSuite links still route correctly.",
)

GOOGLE_DEEPMIND = curated_provider(
    name="Google DeepMind",
    source_url="https://deepmind.google/",
    suffixes=("deepmind.com", "deepmind.google"),
    process=(
        "Keep the DeepMind brand domains only, which is enough for the public web experience "
        "without broadening into unrelated Google infrastructure."
    ),
)

GOOGLE_GENERATIVE_LANGUAGE_API = curated_provider(
    name="Google Generative Language API",
    source_url="https://ai.google.dev/api",
    domains=(
        "generativelanguage.googleapis.com",
        "geller-pa.googleapis.com",
        "proactivebackend-pa.googleapis.com",
    ),
    method="Curated official API baseline from Google's Gemini API documentation.",
    process=(
        "Use the documented Gemini API host and a small set of closely related Google backend "
        "hosts as exact DOMAIN rules so API traffic is captured without proxying broad swaths of "
        "googleapis.com."
    ),
)

GOOGLE_GEMINI = curated_provider(
    name="Google Gemini",
    source_url="https://gemini.google/about/",
    domains=("aisandbox-pa.googleapis.com", "apis.google.com", "robinfrontend-pa.googleapis.com"),
    suffixes=("bard.google.com", "gemini.google", "gemini.google.com"),
    method="Curated official product baseline from Google's Gemini web properties.",
    process=(
        "Keep the current Gemini domains, the legacy Bard compatibility host, and a small set of "
        "exact Google frontend hosts that are closely tied to the Gemini web app."
    ),
)

GOOGLE_NOTEBOOKLM = curated_provider(
    name="Google NotebookLM",
    source_url="https://notebooklm.google/",
    suffixes=("notebooklm.google", "notebooklm.google.com"),
    process=(
        "Use NotebookLM's direct product domains as a conservative baseline and avoid pulling in "
        "broader Google service domains that are not NotebookLM-specific."
    ),
)

GROK = curated_provider(
    name="Grok",
    source_url="https://grok.com/",
    suffixes=("grok.com", "x.ai"),
    process=(
        "Keep xAI's Grok-facing brand domains only, which is the smallest first-party set that "
        "covers the service without guessing at the wider X platform infrastructure."
    ),
)

GROQ = curated_provider(
    name="Groq",
    source_url="https://groq.com/",
    suffixes=("groq.com",),
    process=(
        "Use Groq's primary product domain as a focused DOMAIN-SUFFIX rule for its hosted AI "
        "console and related first-party traffic."
    ),
)

CLIPDROP = curated_provider(
    name="Clipdrop",
    source_url="https://clipdrop.co/",
    suffixes=("clipdrop.co",),
    process=(
        "Use Clipdrop's own product domain as a standalone AI service baseline instead of folding "
        "it into another vendor block."
    ),
)

JASPER = curated_provider(
    name="Jasper",
    source_url="https://www.jasper.ai/",
    suffixes=("jasper.ai",),
    process=(
        "Use Jasper's primary product domain as the first-party baseline and keep the rule tight "
        "instead of bundling in unrelated third-party creative tooling domains."
    ),
)

JETBRAINS_AI = curated_provider(
    name="JetBrains AI",
    source_url="https://www.jetbrains.com/ai/",
    suffixes=("jetbrains.ai",),
    process=(
        "Keep JetBrains AI on its dedicated vendor-owned AI domain family so the service can be "
        "proxied independently from the rest of JetBrains' broader product estate."
    ),
)

META_AI = curated_provider(
    name="Meta AI",
    source_url="https://www.meta.ai/",
    suffixes=("meta.ai",),
    process=(
        "Use Meta AI's own product domain as a minimal first-party baseline and avoid expanding "
        "into the much wider set of general Meta properties."
    ),
)

OPENART = curated_provider(
    name="OpenArt",
    source_url="https://openart.ai/",
    suffixes=("openart.ai",),
    process=(
        "Use OpenArt's primary AI product domain as a compact service baseline without assuming "
        "additional third-party hosts."
    ),
)

OPENROUTER = curated_provider(
    name="OpenRouter",
    source_url="https://openrouter.ai/",
    suffixes=("openrouter.ai",),
    process=(
        "Keep OpenRouter on its first-party domain family so routed model access and console "
        "traffic can be proxied cleanly."
    ),
)

PERPLEXITY = curated_provider(
    name="Perplexity AI",
    source_url="https://www.perplexity.ai/",
    suffixes=("perplexity.ai",),
    process=(
        "Use Perplexity's main product domain as a focused baseline for the public app and search "
        "experience without broadening to unrelated infrastructure."
    ),
)

POE = curated_provider(
    name="Poe",
    source_url="https://poe.com/",
    suffixes=("poe.com",),
    process=(
        "Use Poe's primary product domain as the first-party baseline for chat access and avoid "
        "guessing at its internal CDN or telemetry dependencies."
    ),
)

WINDSURF = curated_provider(
    name="Windsurf",
    source_url="https://windsurf.com/",
    suffixes=("codeium.com", "codeiumdata.com", "windsurf.com"),
    process=(
        "Combine the current Windsurf product domain with the Codeium service families it still "
        "depends on, so both app access and editor-side AI traffic can be routed together."
    ),
)

ZED = curated_provider(
    name="Zed",
    source_url="https://zed.dev/",
    suffixes=("zed.dev",),
    process=(
        "Use Zed's product domain as a conservative first-party baseline for the editor and its "
        "vendor-hosted AI-facing entrypoints."
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
    method="Curated official baseline from Apple's enterprise network guidance.",
    process=(
        "Review Apple's enterprise host tables, keep the stable Apple service families that are "
        "useful as a practical Surge baseline, and collapse many related hosts into a smaller "
        "set of service-oriented DOMAIN-SUFFIX rules."
    ),
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
    method="Curated first-party baseline.",
    process=(
        "Use stable Netflix-owned domain families that consistently cover the main app, media, "
        "images, service operations, and Fast.com, then express them as DOMAIN-SUFFIX rules "
        "without guessing at undocumented third-party delivery endpoints."
    ),
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
    method="Curated first-party baseline.",
    process=(
        "Keep only the obvious Max and HBO Max brand domain families as a conservative starting "
        "point, and avoid expanding into undocumented CDN or telemetry endpoints unless there is "
        "a stronger public source to justify them."
    ),
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
    method="Curated official baseline from TikTok developer documentation.",
    process=(
        "Read TikTok's official developer docs, keep the clearly visible international host "
        "families used for the main site, open APIs, upload APIs, and documented CDN examples, "
        "then emit them as DOMAIN-SUFFIX rules without expanding into speculative ByteDance CDN sets."
    ),
    note=(
        "Conservative international TikTok baseline built from official TikTok developer "
        "docs that explicitly show tiktok.com, open.tiktokapis.com, open-upload.tiktokapis.com, "
        "and tiktokcdn.com. Expand later if you want a broader inferred ByteDance CDN set."
    ),
)

JD_CN = curated_provider(
    name="JD.com (Mainland China)",
    source_url="https://about.jd.com/en/",
    suffixes=("3.cn", "360buy.com", "360buyimg.com", "jd.com", "jdpay.com"),
    method="Curated first-party baseline from JD-owned mainland web properties.",
    process=(
        "Keep the stable JD-operated domain families that consistently cover the mainland web "
        "storefront, short links, first-party static assets, and payment entrypoints, then "
        "express them as DOMAIN-SUFFIX rules without expanding into speculative logistics, cloud, "
        "or unrelated affiliate infrastructure."
    ),
    note=(
        "Built from JD-owned web properties including the corporate site, mainland storefront "
        "family, 3.cn short links, 360buyimg static assets, and JD Pay."
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
    method="Live fetch from Microsoft's official Microsoft 365 endpoint web service with fallback.",
    process=(
        "Request the worldwide Microsoft 365 endpoint JSON feed, convert literal hosts to DOMAIN "
        "rules and wildcard entries to DOMAIN-SUFFIX rules, de-duplicate and sort the result, "
        "and fall back to a core Microsoft productivity baseline if the web service is unavailable."
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
        providers=(
            CLAUDE,
            CLAUDE_CODE,
            OPENAI,
            SORA,
            APPLE_INTELLIGENCE,
            CEREBRAS,
            CHORUS,
            CLOUDFLARE_AI_GATEWAY,
            MICROSOFT_COPILOT,
            GITHUB_COPILOT,
            CURSOR,
            DIA,
            DIFY,
            GOOGLE_AI_STUDIO,
            GOOGLE_DEEPMIND,
            GOOGLE_GENERATIVE_LANGUAGE_API,
            GOOGLE_GEMINI,
            GOOGLE_NOTEBOOKLM,
            GROK,
            GROQ,
            CLIPDROP,
            JASPER,
            JETBRAINS_AI,
            META_AI,
            OPENART,
            OPENROUTER,
            PERPLEXITY,
            POE,
            WINDSURF,
            ZED,
        ),
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
        output_path=Path("jd.list"),
        providers=(JD_CN,),
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


def resolve_provider_rules(provider: Provider) -> ProviderResult:
    if not provider.live_fetch:
        return ProviderResult(
            provider=provider,
            rules=tuple(sort_rules(provider.fallback_rules)),
        )

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
        return ProviderResult(
            provider=provider,
            rules=tuple(sort_rules(provider.fallback_rules)),
            used_fallback=True,
            error=str(exc),
        )
    if rules:
        return ProviderResult(
            provider=provider,
            rules=tuple(rules),
        )

    print(
        f"[warn] {provider.name}: failed to parse official source, using fallback",
        file=sys.stderr,
    )
    return ProviderResult(
        provider=provider,
        rules=tuple(sort_rules(provider.fallback_rules)),
        used_fallback=True,
        error="failed to parse official source",
    )


def load_existing_provider_blocks(
    output_path: Path,
    providers: Iterable[Provider],
) -> dict[str, str]:
    if not output_path.exists():
        return {}

    provider_names = {provider.name for provider in providers}
    blocks: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in output_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# ") and line[2:] in provider_names:
            if current_name is not None:
                blocks[current_name] = "\n".join(current_lines).rstrip()
            current_name = line[2:]
            current_lines = [line]
            continue
        if current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        blocks[current_name] = "\n".join(current_lines).rstrip()

    return blocks


def render_provider_block(provider: Provider, rules: Iterable[RuleEntry]) -> str:
    lines = [
        f"# {provider.name}",
        f"# Source: {provider.source_url}",
    ]
    if provider.method:
        lines.extend(render_comment_block("Method", provider.method))
    if provider.process:
        lines.extend(render_comment_block("Process", provider.process))
    if provider.note:
        lines.extend(render_comment_block("Note", provider.note))
    for rule in rules:
        lines.append(f"{rule.rule_type},{rule.value}")
    return "\n".join(lines).rstrip()


def render_rules(rule_list: RuleList) -> str:
    lines = [
        "# Auto-generated by scripts/update_ai_rules.py.",
        "# Intended for Surge RULE-SET usage.",
        "",
    ]
    existing_blocks = load_existing_provider_blocks(rule_list.output_path, rule_list.providers)

    for provider in rule_list.providers:
        result = resolve_provider_rules(provider)
        if result.used_fallback and provider.name in existing_blocks:
            print(
                f"[warn] {provider.name}: preserving existing block in {rule_list.output_path}",
                file=sys.stderr,
            )
            lines.append(existing_blocks[provider.name])
        else:
            lines.append(render_provider_block(provider, result.rules))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_comment_block(label: str, text: str) -> list[str]:
    wrapped = textwrap.wrap(
        text,
        width=96,
        initial_indent=f"# {label}: ",
        subsequent_indent="#   ",
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [f"# {label}: "]


def main() -> int:
    for rule_list in RULE_LISTS:
        rule_list.output_path.write_text(render_rules(rule_list), encoding="utf-8")
        print(f"Wrote {rule_list.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

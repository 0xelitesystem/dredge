---
title: dredge
emoji: 🔎
colorFrom: gray
colorTo: indigo
sdk: gradio
sdk_version: 5.49.0
app_file: app.py
pinned: false
license: mit
short_description: OSINT toolkit for finding what search engines bury.
---

# dredge

Surface what search engines bury.

An OSINT toolkit for finding suppressed public records, deleted content, and adversarially-buried search results about people and organizations.

## Why

Most due-diligence searches stop at the first page of Google, which is exactly what reputation-management firms pay for. Negative coverage is pushed to page 5+. Tweets and posts get deleted. Court records sit in indexes nobody queries. The loudest paid signal usually outranks the truthful one.

dredge runs adversarial queries in parallel across sources that resist suppression: deep search-engine paging with negative-keyword expansion, the Wayback Machine for deleted content, and court-record APIs for litigation history. Each source is a plugin, three ship today, more are planned.

## Try it

A hosted version runs on Hugging Face Spaces: **[huggingface.co/spaces/0xelitesystem/dredge](https://huggingface.co/spaces/0xelitesystem/dredge)**

Bring your own keys. Nothing is stored. For full control and unlimited use, run it locally, see below.

## Modules

| Module | Source | Required keys |
|---|---|---|
| `google_dork` | Google via SerpAPI, with adversarial keyword expansion | `SERPAPI_KEY` |
| `wayback` | Internet Archive snapshots + deletion detection | none |
| `courtlistener` | U.S. federal & state court records | none (token optional) |

See [Roadmap](#roadmap) for what's coming next.

## Install

```bash
git clone https://github.com/0xelitesystem/dredge.git
cd dredge
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # then fill in keys
```

Python 3.10+.

## Use

```bash
# Most basic
dredge investigate "Jane Doe"

# Person, with aliases and known-good domains (filters out their own PR)
dredge investigate "Jane Doe" \
  --aliases "Janet Doe, J. Doe" \
  --domains "janedoe.com,janedoeproductions.com"

# Company
dredge investigate "Acme Corp" --type company --domains acmecorp.com

# Subset of modules
dredge investigate "Jane Doe" --modules wayback,courtlistener

# Save report
dredge investigate "Jane Doe" -o report.md --json findings.json

# What's installed
dredge list-investigators
```

## How adversarial keyword expansion works

A naive search for `"Jane Doe"` returns Jane's LinkedIn, her company bio, her own podcast appearances. dredge instead generates queries like:

```
"Jane Doe" (scam OR fraud OR sued OR lawsuit OR ripoff) -site:linkedin.com -site:janedoe.com
"Jane Doe" site:reddit.com
"Jane Doe" site:bbb.org
"Jane Doe" inurl:(complaint OR review OR scam OR fraud OR exposed)
```

Multiplied across configurable keyword clusters (fraud, legal, reputation, financial, conduct, crypto), with site-specific sweeps on complaint platforms, and with the target's own domains explicitly excluded.

The clusters live in [`dredge/core/keywords.py`](dredge/core/keywords.py). Tune them per investigation, or add new clusters for specific verticals.

## Architecture

```
dredge/
├── core/
│   ├── investigator.py    Base plugin class
│   ├── runner.py          Async parallel orchestration
│   ├── keywords.py        Adversarial query expansion
│   └── models.py          Target, Finding, Result types
├── investigators/         One file per data source
│   ├── google_dork.py
│   ├── wayback.py
│   └── courtlistener.py
└── reporters/             Output formats
    └── markdown.py
```

Each investigator subclasses `Investigator`, declares which env-var keys it needs, declares which target types it supports, and implements one async method:

```python
async def investigate(self, target: Target) -> list[Finding]: ...
```

The runner resolves which investigators apply, runs them concurrently, and aggregates findings. A failure in one module never breaks the run.

## Adding a module

```python
# dredge/investigators/my_source.py
from ..core.investigator import Investigator
from ..core.models import Target, Finding, SourceType

class MySourceInvestigator(Investigator):
    name = "my_source"
    description = "What this source covers."
    requires_keys = ["MY_API_KEY"]
    supports_types = ["person", "company"]

    async def investigate(self, target: Target) -> list[Finding]:
        # hit your source, return Findings
        ...
```

Register the class in `REGISTRY` in `dredge/cli.py`. Update `.env.example`. Done.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

## Roadmap

Planned modules, ordered by impact:

- **reddit_deep**, Reddit including deleted posts and comments via Pullpush
- **sec_edgar**, SEC filings and enforcement actions
- **ftc_actions**, FTC consumer-protection cases
- **finra_brokercheck**, Securities-industry disciplinary records
- **state_ag**, State Attorney General consent decrees
- **whois_history**, Domain ownership history (SecurityTrails / WhoisXML)
- **etherscan**, On-chain activity for known wallets
- **arkham**, Wallet clustering and labels
- **youtube_transcripts**, Whisper-indexed coverage by investigative channels
- **sherlock**, Username sweep across platforms
- **tos_dr**, Terms-of-Service violations and complaints

Want to write one? See [CONTRIBUTING.md](CONTRIBUTING.md).

## Limits and ethics

- dredge retrieves and aggregates publicly available information. It does not bypass authentication, scrape behind paywalls, or fabricate data.
- Findings are unverified raw evidence. A search hit on a complaint forum is not proof of anything. Read the primary source.
- This tool can be misused. Don't use it to harass, dox, or stalk private individuals. Doing so is wrong and probably illegal where you live.
- The maintainers do not vouch for any specific finding produced by this software.

## License

MIT. Use it, fork it, build on it. Attribution appreciated, not required.

## Acknowledgments

The on-chain forensic methodology that informs several of the planned modules comes from work by ZachXBT, SomaXBT, Hunter, Coffeezilla, Bellingcat, and the broader OSINT community.

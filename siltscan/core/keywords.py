"""Adversarial keyword expansion.

A naive search for a target's name returns the target's own PR.
This module generates query variants designed to surface the
results that reputation-management firms typically push off
page one: complaint forums, court records, deleted reviews.

Clusters are configurable per investigation. Defaults are
conservative. Enable more clusters for deeper sweeps.
"""

KEYWORD_CLUSTERS: dict[str, list[str]] = {
    "fraud": [
        "scam", "scammer", "fraud", "fraudulent",
        "ponzi", "pyramid scheme", "rug pull", "rugpull",
        "exit scam", "ripoff", "ripped off",
    ],
    "legal": [
        "lawsuit", "sued", "litigation", "settlement",
        "indicted", "criminal charges", "complaint filed",
        "consent decree", "cease and desist",
    ],
    "reputation": [
        "exposed", "controversy", "allegations",
        "accused", "scandal", "called out",
    ],
    "financial": [
        "bankruptcy", "default", "insolvency",
        "owes", "unpaid", "wage theft", "chargeback",
    ],
    "conduct": [
        "harassment", "misconduct", "fired",
        "terminated", "banned", "suspended",
    ],
    "crypto": [
        "rug pull", "rugpull", "exit scam",
        "wash trading", "insider", "honeypot",
        "dumped on", "pump and dump",
    ],
}

# Platforms where complaints, reviews, and grievances accumulate.
COMPLAINT_SITES: list[str] = [
    "reddit.com",
    "bbb.org",
    "trustpilot.com",
    "complaintsboard.com",
    "ripoffreport.com",
    "pissedconsumer.com",
    "glassdoor.com",
]

# Domains that almost always serve the target's own PR.
DEFAULT_EXCLUDES: list[str] = [
    "linkedin.com",
    "facebook.com",
    "instagram.com",
]


def build_queries(
    name: str,
    *,
    clusters: list[str] | None = None,
    include_complaint_sites: bool = True,
    exclude_sites: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_queries: int = 25,
) -> list[str]:
    """Generate adversarial search queries for a target name.

    Returns query strings ready for any search API. Order matters:
    cluster sweeps come first (broad), then site-specific sweeps,
    then URL-pattern targeting.
    """
    if clusters is None:
        clusters = ["fraud", "legal", "reputation"]

    excluded = (exclude_sites or DEFAULT_EXCLUDES) + (exclude_domains or [])
    exclude_clause = " ".join(f"-site:{d}" for d in excluded)
    quoted = f'"{name}"'

    queries: list[str] = []

    # Cluster sweeps: one query per cluster, OR-joined terms.
    for cluster in clusters:
        terms = KEYWORD_CLUSTERS.get(cluster, [])
        if not terms:
            continue
        or_clause = " OR ".join(terms[:6])
        q = f"{quoted} ({or_clause})"
        if exclude_clause:
            q = f"{q} {exclude_clause}"
        queries.append(q)

    # Site-specific sweeps on complaint platforms.
    if include_complaint_sites:
        for site in COMPLAINT_SITES:
            queries.append(f"{quoted} site:{site}")

    # URL-pattern targeting catches results other queries miss.
    pattern_q = f"{quoted} inurl:(complaint OR review OR scam OR fraud OR exposed)"
    if exclude_clause:
        pattern_q = f"{pattern_q} {exclude_clause}"
    queries.append(pattern_q)

    return queries[:max_queries]

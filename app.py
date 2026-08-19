"""dredge web interface.

Hugging Face Spaces entry point. Wraps the same Runner / Investigator
pipeline used by the CLI. Keys are taken from the user via password
fields and passed in as a per-request config dict. Never stored,
never logged.
"""

import asyncio
import json
from datetime import datetime, timezone

import gradio as gr

from dredge.core.models import Target, TargetType
from dredge.core.runner import Runner
from dredge.investigators.courtlistener import CourtListenerInvestigator
from dredge.investigators.google_dork import GoogleDorkInvestigator
from dredge.investigators.wayback import WaybackInvestigator
from dredge.reporters.markdown import render as render_markdown


REGISTRY = {
    "google_dork": GoogleDorkInvestigator,
    "wayback": WaybackInvestigator,
    "courtlistener": CourtListenerInvestigator,
}


HEADER = """
# dredge

Surface what search engines bury. An OSINT toolkit for finding suppressed public records, deleted content, and adversarially-buried search results.

**Bring your own keys.** Nothing is stored on this server. Each investigation runs with the keys you provide and is discarded when the page closes. For full control, [run it locally](https://github.com/0xelitesystem/dredge).
"""

DISCLAIMER = """
Findings are unverified raw evidence. A search hit on a complaint forum is not proof of anything. Read the primary source before drawing conclusions. Don't use this to harass private individuals.
"""


def _split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _modules_from_checkboxes(selected: list[str]) -> list[str]:
    return [m for m in REGISTRY if m in selected]


async def _investigate(
    name: str,
    target_type: str,
    aliases: str,
    domains: str,
    selected_modules: list[str],
    serpapi_key: str,
    courtlistener_token: str,
):
    if not name.strip():
        return "Enter a name to investigate.", ""

    target = Target(
        name=name.strip(),
        type=TargetType(target_type),
        aliases=_split(aliases),
        known_domains=_split(domains),
    )

    config: dict[str, str] = {}
    if serpapi_key.strip():
        config["SERPAPI_KEY"] = serpapi_key.strip()
    if courtlistener_token.strip():
        config["COURTLISTENER_TOKEN"] = courtlistener_token.strip()

    investigators = []
    skipped: list[str] = []
    for mod_name in _modules_from_checkboxes(selected_modules):
        cls = REGISTRY[mod_name]
        try:
            investigators.append(cls(config))
        except ValueError as e:
            skipped.append(f"`{mod_name}`: {e}")

    if not investigators:
        msg = "No modules could run. Provide the required keys, or enable a key-free module (wayback, courtlistener)."
        if skipped:
            msg += "\n\nSkipped:\n" + "\n".join(f"- {s}" for s in skipped)
        return msg, ""

    runner = Runner(investigators)
    result = await runner.run(target)

    report = render_markdown(result)
    if skipped:
        report = "## Skipped modules\n\n" + "\n".join(f"- {s}" for s in skipped) + "\n\n---\n\n" + report

    payload = {
        "target": {
            "name": result.target.name,
            "type": result.target.type.value,
            "aliases": result.target.aliases,
            "known_domains": result.target.known_domains,
        },
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        "findings": [f.to_dict() for f in result.findings],
        "errors": result.errors,
    }
    return report, json.dumps(payload, indent=2)


def investigate(
    name, target_type, aliases, domains,
    selected_modules, serpapi_key, courtlistener_token,
):
    return asyncio.run(_investigate(
        name, target_type, aliases, domains,
        selected_modules, serpapi_key, courtlistener_token,
    ))


with gr.Blocks(
    title="dredge",
    theme=gr.themes.Base(
        primary_hue="slate",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    ),
    css="""
    .gradio-container { max-width: 1100px !important; }
    footer { display: none !important; }
    """,
) as demo:
    gr.Markdown(HEADER)

    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### Target")
            name_in = gr.Textbox(
                label="Name",
                placeholder="Person or organization",
                autofocus=True,
            )
            with gr.Row():
                type_in = gr.Dropdown(
                    label="Type",
                    choices=["person", "company", "domain"],
                    value="person",
                )
                aliases_in = gr.Textbox(
                    label="Aliases (comma-separated)",
                    placeholder="J. Doe, Jane Doe",
                )
            domains_in = gr.Textbox(
                label="Known domains owned by target (comma-separated)",
                placeholder="example.com, example.org",
                info="Excluded from search results to filter out their own PR.",
            )

            gr.Markdown("### Modules")
            modules_in = gr.CheckboxGroup(
                choices=list(REGISTRY.keys()),
                value=["wayback", "courtlistener"],
                label="Investigators to run",
                info="google_dork requires a SerpAPI key. The others work without keys.",
            )

        with gr.Column(scale=1):
            gr.Markdown("### Keys")
            gr.Markdown(
                "_Paste keys directly. They live in memory for one request "
                "and are discarded. Never stored, never logged._",
                elem_classes=["small-note"],
            )
            serpapi_in = gr.Textbox(
                label="SerpAPI key",
                type="password",
                placeholder="Required for google_dork",
            )
            courtlistener_in = gr.Textbox(
                label="CourtListener token (optional)",
                type="password",
                placeholder="Higher rate limits if provided",
            )
            gr.Markdown(
                "[Get a SerpAPI key](https://serpapi.com)  -  "
                "[Get a CourtListener token](https://www.courtlistener.com/help/api/rest/)",
            )

    run_btn = gr.Button("Investigate", variant="primary", size="lg")

    with gr.Tabs():
        with gr.Tab("Report"):
            report_out = gr.Markdown()
        with gr.Tab("JSON"):
            json_out = gr.Code(language="json")

    gr.Markdown("---")
    gr.Markdown(DISCLAIMER)

    run_btn.click(
        fn=investigate,
        inputs=[
            name_in, type_in, aliases_in, domains_in,
            modules_in, serpapi_in, courtlistener_in,
        ],
        outputs=[report_out, json_out],
    )


if __name__ == "__main__":
    demo.launch()

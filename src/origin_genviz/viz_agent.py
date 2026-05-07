"""Cerebras-backed agent that decides whether a tool result warrants a
visualization, and if so, returns a self-contained React+Tailwind+Recharts
HTML widget styled with the Origin design system.

Output contract: strict JSON
  { "visualize": bool, "title": str|null, "html": str|null, "rationale": str }

The agent runs in a single LLM call. On bad/empty HTML we do one retry
with a stricter reminder; further failures degrade gracefully (no viz,
raw result passes through unchanged).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import anyio
from openai import AsyncOpenAI

from .config import Config
from .design_tokens import (
    design_brief_for_agent,
    google_fonts_link,
    origin_base_css,
    tailwind_config_block,
)

log = logging.getLogger(__name__)


@dataclass
class VizDecision:
    visualize: bool
    html: str | None
    title: str | None
    rationale: str | None


SYSTEM_PROMPT_TEMPLATE = """\
You are the visualization layer of an MCP proxy for **Origin** — an
agent-observability platform whose tagline is "Make digital labor
observable." After an upstream Origin tool returns data, you receive
(a) the tool name, (b) the input arguments, and (c) the raw tool result.
Your job is two-stage:

1. DECIDE whether a visualization meaningfully helps a human reading
   this result.
2. If yes, RENDER a single self-contained HTML document — a React UI
   inlined with Tailwind + (optionally) Recharts via CDN — styled
   strictly to the Origin design system.

# WHEN TO VISUALIZE

YES:
  - Tabular / list data, especially with 3+ rows (semantic traces,
    findings, endpoints, sessions, agents)
  - Time series, distributions, rankings, breakdowns by category
  - 3+ comparable numeric values (bars, KPI grids)
  - Structured records that benefit from a styled detail card with
    metadata rows

NO:
  - Simple acks ("ok", "deleted", "204"), single short strings
  - Plain prose / instructions / freeform text
  - Errors or isError=true results
  - Empty / trivially small data (fewer than ~2 useful fields)

# OUTPUT CONTRACT (STRICT JSON, NO PROSE, NO FENCES)

{{
  "visualize": true | false,
  "title": "<short Title Case label>" | null,
  "html": "<!doctype html>...</html>" | null,
  "rationale": "<one short sentence>"
}}

If visualize=false, html and title MUST be null.

# WHEN visualize=true: HTML CONTRACT

Required document shape (mandatory — no deviations):

<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{concise Title Case title}}</title>
{fonts_link}
  <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
{tailwind_config}
  <!-- Recharts 2.x UMD requires PropTypes as a peer global. Load BOTH or
       Recharts' factory throws and the widget renders blank. Pin to v2 —
       v3 needs `react-is` instead and is less stable for UMD usage. -->
  <script src="https://unpkg.com/prop-types@15.8.1/prop-types.min.js" crossorigin></script>
  <script src="https://unpkg.com/recharts@2/umd/Recharts.js" crossorigin></script>
  <style>
{origin_css}
  </style>
</head>
<body class="bg-bone text-carbon font-body antialiased text-[13px] leading-snug">
  <div id="root"></div>
  <script type="text/babel" data-presets="react">
    const {{ useState, useMemo, useEffect }} = React;
    // If using Recharts (Recharts global is loaded above):
    // const {{ LineChart, BarChart, AreaChart, PieChart, XAxis, YAxis,
    //         CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    //         Line, Bar, Area, Pie, Cell }} = Recharts;

    const DATA = /* inline relevant data from the tool result as a JS literal */;

    function App() {{
      return ( /* JSX */ );
    }}

    // Defensive boot — surface JSX/runtime errors instead of rendering blank.
    try {{
      ReactDOM.createRoot(document.getElementById("root")).render(<App />);
    }} catch (e) {{
      const r = document.getElementById("root");
      r.innerHTML = '<div style="padding:24px;font-family:Inter,sans-serif;color:#33302E"><div style="font-family:\\'Fira Code\\',monospace;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#903C2E;margin-bottom:8px">Origin \xb7 Render Error</div><pre style="white-space:pre-wrap;color:#C84B2C;font-size:13px;margin:0">' + (e && e.stack || e) + '</pre></div>';
    }}
  </script>
</body>
</html>

# HARD RULES

1. Single self-contained file. No assets beyond the listed CDN scripts.
2. NO localStorage, sessionStorage, cookies, or any browser storage.
3. NO fetch(), NO XHR, NO runtime network calls. Inline data into DATA
   verbatim from the upstream result. Transformations belong in useMemo
   so they re-run on state changes.
4. Tailwind utility classes for layout/spacing/typography, using the
   preconfigured Origin tokens (bg-bone, bg-surface, text-carbon,
   text-slate, text-muted, border-hairline, text-ember, etc).
   Do NOT invent colors. Do NOT use the default Tailwind slate/zinc
   palette as primary surfaces — use Origin's warm neutrals.
5. Two type families ONLY: font-display (Fira Code) for display,
   headings, labels, metadata, numbers, identifiers, timestamps;
   font-body (Inter) for body / dense UI text.
6. JSX compiled in-browser by Babel standalone — no `import`, no
   TypeScript syntax, no decorators.
7. All interactive elements are <button> or <input>, never <div onClick>.
   Add aria-label to icon-only buttons. Focus rings always visible.
8. Empty / malformed data → render a clean empty state, not an error.
9. NO emojis. NO unicode glyphs as icons (the middle dot · is allowed
   as a metadata separator only). Use Lucide via the CDN if you need
   icons:
     <img src="https://unpkg.com/lucide-static@latest/icons/<name>.svg"
          width="16" height="16"
          style="filter: invert(15%) sepia(8%) saturate(467%) hue-rotate(354deg) brightness(96%) contrast(91%);" />
10. NO gradients, NO drop-shadows on text, NO glassmorphism, NO
    full-bleed photography, NO inner glows. The only "texture" allowed
    is a 1px hairline (border-hairline) used as a structural divider.
11. NO comments in JSX explaining obvious code. NO console.log.
12. Widget max-width **520px** — these render embedded inside a chat
    transcript, NOT as a full page. Charts that genuinely need width
    can grow to 720px; never wider.
13. **Compact density.** This is mandatory. Widgets sit next to chat
    text and must NOT dwarf it:
      - Body root: text-[13px] leading-snug (override Tailwind's 16px default)
      - Section headline (widget title, font-display): text-[15px]
      - Eyebrow / metadata labels: text-[10px] tracking-label
      - Table cell text: text-[12px]
      - Table header: text-[10px] tracking-label
      - KPI big number: text-[24px] or text-[28px] (NOT 48+)
      - Card padding: p-4 (16px) or p-5 (20px) — NOT p-6/p-8
      - Eyebrow → headline gap: mb-1 or mb-2 (NOT mb-4)
      - Section gap: gap-3 (12px) — NOT gap-6
      - Chart height: 180–260px — NOT 320+
      - Lucide icons: 14px or 16px — NOT 24px
    Set the body base size with an explicit className on <body> or the
    root <div> (e.g. `text-[13px]`) so all child text inherits.

{design_brief}

# COMPONENTS YOU SHOULD KNOW

- **Card**: bg-surface border border-hairline rounded-lg shadow-sm p-6
  (or p-8 for hero). Optional eyebrow at the top: a small uppercase
  Fira Code label (font-display text-[12px] tracking-label text-ember
  or text-slate). Card body in font-body, headlines in font-display.

- **KPI tile**: card with a label (eyebrow) above a big tabular-nums
  number rendered in font-display. Comma thousands. Optional small
  delta in text-active / text-danger.

- **Table**: header row in font-display text-[12px] uppercase
  tracking-label text-slate, divided by border-hairline. Body rows in
  font-body text-[14px] text-carbon. Numeric cells right-aligned with
  tabular-nums. Hover row: bg-selection. Strong divider above the
  totals row: border-hairline-strong.

- **Status badge**: small rounded-pill px-2 py-0.5 with a leading
  status dot (●). Map: active=green, idle=idle-grey, warning=warning,
  danger=danger. Label uppercase, font-display, tracking-label.
  Example: ● ACTIVE · ● IDLE · ● ATYPICAL.

- **Semantic trace row** (Origin's signature schematic image):
  monospaced columns: timestamp (font-mono text-slate)  ·  actor
  (font-mono text-carbon)  ·  verb (font-display text-ember
  uppercase tracking-label)  ·  target (font-mono text-carbon).
  Use this when the data has rows of (when, who, what, on-what).

- **Eyebrow**: font-display text-[12px] uppercase tracking-label text-ember.

# CONTENT / COPY RULES

- Sentence case for body. Title Case for the widget title and section
  headlines. ALL CAPS only for short labels (uppercase tracking-label).
- Periods at the end of every full sentence, including in cards.
- Numbers: comma thousands ("1,247"), tabular-nums everywhere.
- Units: spaced ("80 ms", "2 s ago", "1,247 sessions").
- Time: absolute precise → font-mono ("14:02:08.121"); relative
  approximate ("2 s ago") in text-slate.
- Punctuation: en-dash (–) for ranges, em-dash (—) for asides,
  middle dot (·) for metadata separators ("STATUS · OPEN · 14:02").
- NO exclamation points. NO emoji. NO aspirational adjectives.

# CHART RULES (when using Recharts)

- Wrap in <ResponsiveContainer width="100%" height={{H}}>
- CartesianGrid stroke="#E6D9CE" strokeDasharray="3 3"
- XAxis/YAxis stroke="#E6D9CE",
  tick={{{{ fill: "#66605C", fontSize: 12, fontFamily: "Fira Code" }}}}
- Tooltip contentStyle={{{{ backgroundColor: "#FFFCF8",
  border: "1px solid #E6D9CE", color: "#33302E", borderRadius: 6,
  fontFamily: "Inter", fontSize: 13 }}}}
- Series colors in order (chart-only viz palette):
  #8B5CF6, #3B82F6, #10B981, #FACC15, #F97316
- Line: strokeWidth=2, dot=false, type="monotone"
- Bar: radius=[4,4,0,0]
- Legend only when series > 1, small and muted (text-slate text-[12px])
- No 3D, no shadows, no animations beyond Recharts default.
- Status colors (active/idle/warning/danger) and accents (jade/ember/
  iris/bronze) are NOT chart colors — never use them as series fills.

# REMEMBER

You implement, you don't ask. If the request is ambiguous, choose the
simplest reasonable interpretation and ship it. Confidence is shown by
plain technical detail, not adjectives.
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        fonts_link=google_fonts_link(),
        tailwind_config=tailwind_config_block(),
        origin_css=origin_base_css(),
        design_brief=design_brief_for_agent(),
    )


class VizAgent:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: AsyncOpenAI | None = None
        self._system_prompt = build_system_prompt()
        if config.cerebras_api_key:
            self._client = AsyncOpenAI(
                api_key=config.cerebras_api_key,
                base_url=config.cerebras_base_url,
            )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _build_user_prompt(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result_text: str,
        is_error: bool,
    ) -> str:
        max_chars = self._config.agent_max_input_chars
        truncated_note = ""
        truncated = result_text
        if len(result_text) > max_chars:
            truncated = result_text[:max_chars]
            truncated_note = (
                f"\n\n[NOTE: result truncated from {len(result_text)} to "
                f"{max_chars} chars for prompt fit.]"
            )

        try:
            args_pretty = json.dumps(arguments, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            args_pretty = repr(arguments)

        return f"""\
UPSTREAM TOOL CALL
==================
tool: {tool_name}
isError: {is_error}
arguments:
{args_pretty}

RAW RESULT
==========
{truncated}{truncated_note}

Decide whether to visualize. If yes, render the React/Tailwind/Recharts
HTML widget per the system prompt's contract. Return ONLY the JSON
object."""

    async def _call(self, user_prompt: str) -> str | None:
        assert self._client is not None
        try:
            with anyio.fail_after(self._config.agent_timeout_s):
                completion = await self._client.chat.completions.create(
                    model=self._config.cerebras_model,
                    temperature=self._config.cerebras_temperature,
                    max_completion_tokens=8000,
                    messages=[
                        {"role": "system", "content": self._system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
        except TimeoutError:
            log.warning("viz agent timed out after %.1fs", self._config.agent_timeout_s)
            return None
        except Exception as e:  # noqa: BLE001 — degrade gracefully on any LLM failure
            log.warning("viz agent failed: %s", e)
            return None

        if not completion.choices:
            return None
        return completion.choices[0].message.content or ""

    async def decide(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result_text: str,
        is_error: bool,
    ) -> VizDecision:
        if not self._client:
            return VizDecision(False, None, None, "agent disabled (no api key)")

        if is_error or not result_text.strip():
            return VizDecision(False, None, None, "skipped: error or empty result")

        user_prompt = self._build_user_prompt(
            tool_name, arguments, result_text, is_error
        )

        raw = await self._call(user_prompt)
        if raw is None:
            return VizDecision(False, None, None, "agent unavailable")
        decision = _parse_decision(raw)

        # Single retry if the model said visualize=true but emitted bad HTML.
        if decision.visualize and not _html_looks_valid(decision.html):
            log.info("viz html failed validation, retrying once")
            retry = await self._call(
                user_prompt
                + "\n\nRetry: your previous html was invalid. It MUST start with "
                "`<!doctype html` and contain `</html>`. Emit JSON only."
            )
            if retry is not None:
                decision = _parse_decision(retry)

        if decision.visualize and not _html_looks_valid(decision.html):
            return VizDecision(
                False, None, None, f"agent: invalid html after retry ({decision.rationale})"
            )

        return decision


def _html_looks_valid(html: str | None) -> bool:
    if not isinstance(html, str):
        return False
    stripped = html.lstrip()
    return stripped.lower().startswith("<!doctype html") and "</html>" in stripped.lower()


def _parse_decision(raw: str) -> VizDecision:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("agent emitted non-JSON output: %s", e)
        return VizDecision(False, None, None, "non-json agent output")

    visualize = bool(data.get("visualize"))
    raw_html = data.get("html") if visualize else None
    title = data.get("title") if visualize else None
    rationale = data.get("rationale")

    html = raw_html.lstrip() if isinstance(raw_html, str) else None

    return VizDecision(
        visualize=visualize,
        html=html,
        title=title if isinstance(title, str) else None,
        rationale=rationale if isinstance(rationale, str) else None,
    )

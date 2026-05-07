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
from .design_tokens import design_brief_for_agent, tailwind_config_block

log = logging.getLogger(__name__)


@dataclass
class VizDecision:
    visualize: bool
    html: str | None
    title: str | None
    rationale: str | None


SYSTEM_PROMPT_TEMPLATE = """\
You are the visualization layer of an MCP proxy. After an upstream tool
returns data, you receive (a) the tool name, (b) the input arguments,
and (c) the raw tool result. Your job is two-stage:

1. DECIDE whether a visualization meaningfully helps a human reading
   this result.
2. If yes, RENDER a single self-contained HTML document — a React UI
   inlined with Tailwind + (optionally) Recharts via CDN — styled
   exactly to the Origin design system.

# WHEN TO VISUALIZE

YES:
  - Tabular / list data, especially with 3+ rows
  - Time series, distributions, rankings, breakdowns by category
  - 3+ comparable numeric values (bars, KPI grids)
  - Structured records that benefit from a styled detail card

NO:
  - Simple acks ("ok", "deleted", "204"), single short strings
  - Plain prose / instructions / freeform text
  - Errors or isError=true results
  - Empty / trivially small data (fewer than ~2 useful fields)

# OUTPUT CONTRACT (STRICT JSON, NO PROSE, NO FENCES)

{{
  "visualize": true | false,
  "title": "<short label>" | null,
  "html": "<!doctype html>...</html>" | null,
  "rationale": "<one short sentence>"
}}

If visualize=false, html and title MUST be null. Do not waste tokens
on an unused html field.

# WHEN visualize=true: HTML CONTRACT

Required document shape (this is mandatory — no deviations):

<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{concise title}}</title>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
{tailwind_config}
  <!-- Include Recharts ONLY if rendering charts: -->
  <script src="https://unpkg.com/recharts/umd/Recharts.js"></script>
  <style>
    html, body {{ background: #0B0D10; color: #E6EDF3; margin: 0; }}
    * {{ box-sizing: border-box; }}
    .tabular-nums {{ font-variant-numeric: tabular-nums; }}
  </style>
</head>
<body class="bg-origin-bg text-origin-text font-sans antialiased">
  <div id="root"></div>
  <script type="text/babel" data-presets="react">
    const {{ useState, useMemo, useEffect }} = React;
    // If Recharts:
    // const {{ LineChart, BarChart, AreaChart, PieChart, XAxis, YAxis,
    //         CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    //         Line, Bar, Area, Pie, Cell }} = Recharts;

    const DATA = /* inline the relevant data from the tool result as a JS literal */;

    function App() {{
      // logic here
      return ( /* JSX */ );
    }}

    ReactDOM.createRoot(document.getElementById("root")).render(<App />);
  </script>
</body>
</html>

# HARD RULES

1. Single self-contained file. No assets beyond the listed CDN scripts.
2. NO localStorage, sessionStorage, cookies, or any browser storage.
3. NO fetch(), NO XHR, NO runtime network calls. Inline data into DATA
   verbatim from the upstream result. Do not paraphrase or summarize at
   generation time — transformations belong in useMemo so they re-run
   on state changes.
4. Tailwind utility classes for layout/spacing/typography. Use the
   preconfigured `origin-*` color tokens (bg-origin-surface, text-origin-text,
   border-origin-border, etc). Do not invent colors; do not use the
   default Tailwind slate/zinc palette for primary surfaces.
5. JSX is compiled in-browser by Babel standalone — no `import`,
   no TypeScript syntax, no decorators.
6. All interactive elements are <button> or <input>, never <div onClick>.
   Add aria-label to icon-only buttons.
7. Empty / malformed data → render a clean empty state, not an error.
8. No emojis as iconography. Use inline SVG or Unicode geometric shapes
   if needed. No "AI tells": generic hero copy, rainbow gradients,
   glassmorphism, lorem ipsum.
9. No comments inside the JSX explaining obvious code. No console.log.
10. Page max-width should be ~640px unless a chart inherently needs more.

{design_brief}

# COMPONENTS YOU SHOULD KNOW

- KPI cards: bg-origin-surface border border-origin-border rounded-lg p-5,
  big tabular-nums value, small uppercase label in text-origin-text-muted
- Tables: thin border-origin-border dividers, header text-[11px] uppercase
  tracking-wide text-origin-text-muted, optional bg-origin-surface-alt zebra
- Status badges: rounded-full px-2.5 py-0.5 text-xs font-medium; map status
  → success/warn/error palette
- Filter chips, segmented controls, tabs (underline active state)

# CHART HINTS (when using Recharts)

- Wrap in <ResponsiveContainer width="100%" height={{H}}>
- CartesianGrid stroke="#21262D" strokeDasharray="3 3"
- XAxis/YAxis stroke="#21262D", tick={{{{ fill: "#484F58", fontSize: 11 }}}}
- Tooltip contentStyle={{{{ backgroundColor: "#13161B", border: "1px solid #21262D", color: "#E6EDF3", borderRadius: 8 }}}}
- Series palette in order: #5B8CFF, #7CCAFC, #A371F7, #3FB950, #D29922, #F85149
- Line: strokeWidth=2, dot=false, type="monotone"
- Bar: radius=[4,4,0,0]
- Legend only when series > 1

# REMEMBER

You implement, you don't ask. The user will not see clarifying questions.
If the request is ambiguous, choose the simplest reasonable interpretation
and ship it.
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        tailwind_config=tailwind_config_block(),
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

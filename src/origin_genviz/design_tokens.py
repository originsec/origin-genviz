"""Origin design system tokens for runtime use.

The canonical reference lives in `docs/origin-design/colors_and_type.css`
(also kept as a string here for self-containment when the agent inlines
it into a generated HTML widget). The Tailwind config block exposes the
tokens with class names that match the semantic vocabulary of the design
system — bone, surface, carbon, ember, jade, hairline, viz, etc.

Constraints lifted from the Origin spec:
  - ~90% warm neutrals (bone / surface / carbon)
  - Accents (jade / ember / iris / bronze) appear once per moment, never
    as ambient surface
  - Status colors (active / idle / warning / danger) are functional
  - Viz palette is chart-only
  - Internal-comms palette is employee-facing only — NOT exposed here
    to discourage accidental use in customer-facing visualizations
"""
from __future__ import annotations

# Canonical Origin tokens — keep in sync with docs/origin-design/colors_and_type.css
ORIGIN_TOKENS = {
    "neutral": {
        "bone": "#FFF1E5",
        "surface": "#FFFCF8",
        "muted": "#99918A",
        "slate": "#66605C",
        "carbon": "#33302E",
        "obsidian": "#1A1614",
    },
    "accent": {
        "jade": "#4E848C",
        "ember": "#903C2E",
        "iris": "#6B5FA8",
        "bronze": "#97753E",
    },
    "interactive": {
        "border": "#E6D9CE",
        "border_strong": "#C4B8AC",
        "selection": "#EDD9C4",
    },
    "status": {
        "active": "#22C55E",
        "idle": "#C0B6AE",
        "warning": "#F59E0B",
        "danger": "#C84B2C",
    },
    "viz": {
        # Use this exact ordering as the chart series sequence.
        "crimson": "#8B2332",
        "blue": "#3B82F6",
        "green": "#10B981",
        "yellow": "#FACC15",
        "orange": "#F97316",
    },
    "type": {
        "display": '"Fira Code", ui-monospace, "SF Mono", Menlo, Consolas, monospace',
        "body": '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif',
    },
    "radius": {
        "xs": "2px",
        "sm": "4px",
        "md": "6px",
        "lg": "10px",
        "xl": "16px",
        "pill": "999px",
    },
    "shadow": {
        "xs": "0 1px 0 rgba(26, 22, 20, 0.04)",
        "sm": "0 1px 2px rgba(26, 22, 20, 0.06), 0 1px 1px rgba(26, 22, 20, 0.04)",
        "md": "0 4px 12px rgba(26, 22, 20, 0.06), 0 1px 2px rgba(26, 22, 20, 0.04)",
        "lg": "0 12px 28px rgba(26, 22, 20, 0.08), 0 2px 4px rgba(26, 22, 20, 0.05)",
        "xl": "0 24px 60px rgba(26, 22, 20, 0.12), 0 4px 8px rgba(26, 22, 20, 0.06)",
    },
    "viz_sequence": ["crimson", "blue", "green", "yellow", "orange"],
}


def google_fonts_link() -> str:
    """Drop into <head> to load Fira Code + Inter."""
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?'
        "family=Fira+Code:wght@400;500;600;700"
        "&family=Inter:wght@300;400;500;600;700;800"
        '&display=swap" rel="stylesheet">'
    )


def tailwind_config_block() -> str:
    """A <script> block configuring Tailwind with Origin tokens.

    Drop immediately after the Tailwind CDN <script>. Lets the agent
    write idiomatic Tailwind: bg-bone, text-carbon, border-hairline,
    text-ember, bg-viz-crimson, font-display, etc.
    """
    n = ORIGIN_TOKENS["neutral"]
    a = ORIGIN_TOKENS["accent"]
    i = ORIGIN_TOKENS["interactive"]
    s = ORIGIN_TOKENS["status"]
    v = ORIGIN_TOKENS["viz"]
    r = ORIGIN_TOKENS["radius"]
    sh = ORIGIN_TOKENS["shadow"]

    return f"""\
<script>
  tailwind.config = {{
    theme: {{
      extend: {{
        colors: {{
          bone: "{n['bone']}",
          surface: "{n['surface']}",
          muted: "{n['muted']}",
          slate: "{n['slate']}",
          carbon: "{n['carbon']}",
          obsidian: "{n['obsidian']}",
          jade: "{a['jade']}",
          ember: "{a['ember']}",
          iris: "{a['iris']}",
          bronze: "{a['bronze']}",
          hairline: {{ DEFAULT: "{i['border']}", strong: "{i['border_strong']}" }},
          selection: "{i['selection']}",
          active: "{s['active']}",
          idle: "{s['idle']}",
          warning: "{s['warning']}",
          danger: "{s['danger']}",
          viz: {{
            crimson: "{v['crimson']}",
            blue: "{v['blue']}",
            green: "{v['green']}",
            yellow: "{v['yellow']}",
            orange: "{v['orange']}"
          }}
        }},
        fontFamily: {{
          display: ["Fira Code", "ui-monospace", "SF Mono", "Menlo", "Consolas", "monospace"],
          mono:    ["Fira Code", "ui-monospace", "SF Mono", "Menlo", "Consolas", "monospace"],
          body:    ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "system-ui", "sans-serif"],
          sans:    ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "system-ui", "sans-serif"]
        }},
        letterSpacing: {{
          display: "-0.03em",
          "display-tight": "-0.04em",
          subhead: "0.02em",
          label: "0.08em"
        }},
        borderRadius: {{
          xs: "{r['xs']}", sm: "{r['sm']}", md: "{r['md']}", lg: "{r['lg']}", xl: "{r['xl']}", pill: "{r['pill']}"
        }},
        boxShadow: {{
          xs: "{sh['xs']}",
          sm: "{sh['sm']}",
          md: "{sh['md']}",
          lg: "{sh['lg']}",
          xl: "{sh['xl']}"
        }}
      }}
    }}
  }};
</script>
""".strip()


def origin_base_css() -> str:
    """A compact subset of colors_and_type.css to inline alongside Tailwind.

    Carries the CSS custom properties (so non-Tailwind selectors work) and
    a few element defaults.
    """
    n = ORIGIN_TOKENS["neutral"]
    a = ORIGIN_TOKENS["accent"]
    i = ORIGIN_TOKENS["interactive"]
    s = ORIGIN_TOKENS["status"]
    v = ORIGIN_TOKENS["viz"]
    return f"""\
:root {{
  --color-bone: {n['bone']};
  --color-surface: {n['surface']};
  --color-muted: {n['muted']};
  --color-slate: {n['slate']};
  --color-carbon: {n['carbon']};
  --color-obsidian: {n['obsidian']};
  --color-jade: {a['jade']};
  --color-ember: {a['ember']};
  --color-iris: {a['iris']};
  --color-bronze: {a['bronze']};
  --color-border: {i['border']};
  --color-border-strong: {i['border_strong']};
  --color-selection: {i['selection']};
  --color-active: {s['active']};
  --color-idle: {s['idle']};
  --color-warning: {s['warning']};
  --color-danger: {s['danger']};
  --color-viz-crimson: {v['crimson']};
  --color-viz-blue: {v['blue']};
  --color-viz-green: {v['green']};
  --color-viz-yellow: {v['yellow']};
  --color-viz-orange: {v['orange']};
  --font-display: "Fira Code", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --font-body: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
}}
html, body {{
  margin: 0;
  background: var(--color-bone);
  color: var(--color-carbon);
  font-family: var(--font-body);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}}
* {{ box-sizing: border-box; }}
.tabular-nums {{ font-variant-numeric: tabular-nums; }}
::selection {{ background: var(--color-selection); color: var(--color-carbon); }}
"""


def design_brief_for_agent() -> str:
    """Compact, prescriptive Origin brief baked into the agent system prompt."""
    n = ORIGIN_TOKENS["neutral"]
    a = ORIGIN_TOKENS["accent"]
    i = ORIGIN_TOKENS["interactive"]
    s = ORIGIN_TOKENS["status"]
    v = ORIGIN_TOKENS["viz"]
    return f"""\
ORIGIN DESIGN SYSTEM — warm-neutral, code-native, light-theme.
Origin is the agent-observability platform. Tagline: "Make digital labor observable."
Tone: precise, technical, plain-spoken. Confident, never hyped.

PALETTE (Tailwind classes are preconfigured):
  Neutrals (90% of real estate):
    bone {n['bone']}        → bg-bone (page background)
    surface {n['surface']}     → bg-surface (cards, elevated)
    muted {n['muted']}       → text-muted (de-emphasised)
    slate {n['slate']}       → text-slate (secondary text)
    carbon {n['carbon']}      → text-carbon (primary text)
    obsidian {n['obsidian']}    → bg-obsidian (inverse / dark CTA bands)
  Hairlines (1px borders only):
    hairline {i['border']}     → border-hairline
    hairline-strong {i['border_strong']} → border-hairline-strong (table rules, emphasis)
  Accents (USE ONCE PER MOMENT — a tag, a callout, a section rule. NEVER as ambient bg):
    jade {a['jade']}        → text-jade
    ember {a['ember']}       → text-ember (eyebrow labels)
    iris {a['iris']}        → text-iris
    bronze {a['bronze']}      → text-bronze
  Status (FUNCTIONAL ONLY — system state, never decorative):
    active {s['active']}      → text-active / bg-active (active dot)
    idle {s['idle']}        → text-idle
    warning {s['warning']}     → text-warning
    danger {s['danger']}      → text-danger
  Viz palette (CHART MARKS ONLY — never UI chrome). Use in this order:
    viz.crimson {v['crimson']}  → bg-viz-crimson / fill="#8B2332"
    viz.blue   {v['blue']}    → bg-viz-blue
    viz.green  {v['green']}   → bg-viz-green
    viz.yellow {v['yellow']}  → bg-viz-yellow
    viz.orange {v['orange']}  → bg-viz-orange

TYPOGRAPHY (two families, NO exceptions):
  Fira Code (font-display / font-mono): all display, headings, subheads,
  labels, metadata, timestamps, counts, identifiers.
  Inter (font-body / font-sans): body copy, dense UI text.
  Display tracking: -0.03em (-0.04em at the largest sizes).
  Subhead tracking: +0.02em.
  Uppercase labels: +0.08em (use .tracking-label).
  Body in EMBEDDED widgets sits at 13 px (chat-density override of the
  full-page 14 px floor — these widgets render inside a chat transcript,
  not as standalone pages).
  Numbers ALWAYS tabular-nums. Comma thousands separators ("1,247").
  Units spaced from numbers ("80 ms", "2 s ago").

CASING:
  Sentence case for body and most UI labels.
  Title Case for display headlines ("Findings By Status").
  ALL CAPS + tracking-label only for status / metadata labels
  ("STATUS · OPEN", "LAST SEEN", "SESSIONS"). Never ALL CAPS for full sentences.
  Periods at the end of every full sentence — including in cards.

PUNCTUATION:
  En-dash (–) for ranges. Em-dash (—) for asides.
  Middle dot (·) as a metadata separator ("STATUS · OPEN · 14:02").

NUMBERS / DATA:
  Tabular figures, comma thousands, spaced units.
  Time absolute when precise ("14:02:08.121", monospaced),
  relative when approximate ("2 s ago").

LAYOUT — embedded-in-chat density (NOT full-page):
  Widget max-width: 520 px. Charts that genuinely need width can grow to 720 px.
  Background: bg-bone almost always. bg-obsidian only for stats bands / dark CTAs.
  Cards: bg-surface border border-hairline rounded-lg shadow-sm p-4 (16px) or p-5 (20px).
  An "eyebrow" label sits at the top of cards (uppercase Fira Code, ember or slate),
  not a heavy header bar.
  Sizes: body text-[13px], headline text-[15px] font-display, eyebrow/label
  text-[10px] tracking-label, table cell text-[12px], KPI number text-[24–28px],
  chart height 180–260 px, Lucide icons 14–16 px.
  Card-internal gap-3 (12 px); section gap-3/gap-4. Tight density with one
  unit of breathing room between groups — NOT generous full-page whitespace.

VISUAL TEXTURE: the only allowed texture is a 1px hairline rule. NO gradients, NO patterns,
  NO drop shadows on text, NO glassmorphism, NO full-bleed photography, NO inner glows.

CORNER RADII: 6 px on inputs/buttons (rounded-md), 10 px on cards (rounded-lg),
  16 px on hero cards (rounded-xl), pill on tags. Nothing rounder than pill.

ICONOGRAPHY: Lucide only, stroke 1.5, round caps & joins. No emoji. No unicode glyphs as icons
  except middle dot (·) as a metadata separator. To use Lucide in a CDN-loaded prototype:
    <img src="https://unpkg.com/lucide-static@latest/icons/<name>.svg" width="16" height="16"
         style="filter: invert(15%) sepia(8%) saturate(467%) hue-rotate(354deg) brightness(96%) contrast(91%);" />
  Default stroke color is carbon (#33302E); use slate for de-emphasis, status colors for system state.

CHART RULES (Recharts):
  - Wrap in <ResponsiveContainer width="100%" height={{H}}>
  - CartesianGrid stroke="#E6D9CE" strokeDasharray="3 3"
  - XAxis/YAxis stroke="#E6D9CE", tick={{{{ fill: "#66605C", fontSize: 12, fontFamily: "Fira Code" }}}}
  - Tooltip contentStyle={{{{ backgroundColor: "#FFFCF8", border: "1px solid #E6D9CE",
      color: "#33302E", borderRadius: 6, fontFamily: "Inter", fontSize: 13 }}}}
  - Series colors in order: #8B2332, #3B82F6, #10B981, #FACC15, #F97316
  - Line: strokeWidth=2, dot=false, type="monotone"
  - Bar: radius=[4,4,0,0]
  - Legend only when series > 1, small and muted (text-slate text-[12px])
  - No 3D, no shadows, no animations beyond Recharts default.

VOICE / COPY:
  Plain-spoken, technical, declarative. Verbs concrete (capture, query, surface, flag).
  Never aspirational adjectives. No exclamation points. No emoji.
  Third-person product-as-subject for descriptions ("Origin captures…").
  Second person for action prompts ("View trace", "Connect endpoint").
"""


# Backwards-compatible alias retained for older callers.
def base_stylesheet() -> str:
    return origin_base_css()

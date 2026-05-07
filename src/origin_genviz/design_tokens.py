"""Origin design system tokens, baked into the agent's HTML output.

Tokens here are a reasonable Origin-flavored dark theme. Tune these to
match the canonical Origin design system once accessible — the agent
just substitutes them into the system prompt and Tailwind config, so
changes here propagate immediately to all generated visualizations.
"""

from __future__ import annotations

ORIGIN_TOKENS = {
    "color": {
        "bg": "#0B0D10",
        "surface": "#13161B",
        "surface_alt": "#1B2027",
        "border": "#21262D",
        "text": "#E6EDF3",
        "text_muted": "#7D8590",
        "text_dim": "#484F58",
        "accent": "#5B8CFF",
        "accent_soft": "#1F2D4A",
        "success": "#3FB950",
        "warn": "#D29922",
        "error": "#F85149",
        "chart": [
            "#5B8CFF",
            "#7CCAFC",
            "#A371F7",
            "#3FB950",
            "#D29922",
            "#F85149",
            "#79C0FF",
            "#56D364",
        ],
    },
    "type": {
        "family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "mono": "'JetBrains Mono', 'SF Mono', Menlo, monospace",
    },
    "radius": "10px",
    "radius_sm": "6px",
    "radius_lg": "14px",
    "spacing_unit": "8px",
    "shadow": "0 1px 2px rgba(0,0,0,.3), 0 4px 16px rgba(0,0,0,.25)",
}


def tailwind_config_block() -> str:
    """A <script> block configuring Tailwind with Origin tokens.

    Drop this immediately after the Tailwind CDN <script>. Lets the agent
    write Tailwind utilities like bg-origin-surface, text-origin-text,
    border-origin-border, etc.
    """
    c = ORIGIN_TOKENS["color"]
    chart_entries = ", ".join(f'"chart-{i + 1}": "{v}"' for i, v in enumerate(c["chart"]))
    return f"""
<script>
  tailwind.config = {{
    theme: {{
      extend: {{
        colors: {{
          origin: {{
            bg: "{c['bg']}",
            surface: "{c['surface']}",
            "surface-alt": "{c['surface_alt']}",
            border: "{c['border']}",
            text: "{c['text']}",
            "text-muted": "{c['text_muted']}",
            "text-dim": "{c['text_dim']}",
            accent: "{c['accent']}",
            "accent-soft": "{c['accent_soft']}",
            success: "{c['success']}",
            warn: "{c['warn']}",
            error: "{c['error']}",
            {chart_entries}
          }}
        }},
        fontFamily: {{
          sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
          mono: ["JetBrains Mono", "SF Mono", "Menlo", "monospace"]
        }},
        borderRadius: {{
          DEFAULT: "{ORIGIN_TOKENS['radius']}",
          sm: "{ORIGIN_TOKENS['radius_sm']}",
          lg: "{ORIGIN_TOKENS['radius_lg']}"
        }}
      }}
    }}
  }};
</script>
""".strip()


def design_brief_for_agent() -> str:
    """Compact, prescriptive description of Origin look & feel for the LLM."""
    c = ORIGIN_TOKENS["color"]
    return f"""\
ORIGIN DESIGN SYSTEM — dark, restrained, dense.

Palette (Tailwind theme is preconfigured with these as `origin-*`):
  bg                  {c['bg']}      → bg-origin-bg
  surface             {c['surface']}    → bg-origin-surface (cards)
  surface-alt         {c['surface_alt']}    → bg-origin-surface-alt (hover/zebra)
  border              {c['border']}    → border-origin-border
  text                {c['text']}    → text-origin-text
  text-muted          {c['text_muted']}    → text-origin-text-muted (labels, secondary)
  text-dim            {c['text_dim']}    → text-origin-text-dim (captions, axis ticks)
  accent              {c['accent']}    → text-origin-accent / bg-origin-accent (single accent, sparingly)
  accent-soft         {c['accent_soft']}    → bg-origin-accent-soft (accent backgrounds)
  success             {c['success']}    → semantic green
  warn                {c['warn']}    → semantic amber
  error               {c['error']}    → semantic red
  chart sequence (use in this order): origin-chart-1..8 → {', '.join(c['chart'])}

Typography:
  font-sans (Inter, system-ui fallbacks). font-mono for IDs, hashes, code.
  page title: text-lg font-semibold tracking-tight
  section labels: text-[11px] font-medium uppercase tracking-[0.06em] text-origin-text-muted
  body: text-[13px] leading-relaxed
  numbers / KPIs: tabular-nums

Layout:
  page wrapper: max-w-[640px] mx-auto p-6 (or wider only when a chart needs it)
  cards: bg-origin-surface border border-origin-border rounded-lg p-5
  card spacing: gap-4
  no gradients, no glassmorphism, no drop-shadows on text
  density tight, generous whitespace between groups, no decorative chrome

Charts (Recharts):
  axis stroke: {c['border']}, axis tick text: text-origin-text-dim
  gridlines: stroke {c['border']} at opacity ~0.6, dashed (strokeDasharray="3 3")
  series colors: origin-chart-1, origin-chart-2, ... in order
  Line: strokeWidth=2, dot=false, type="monotone"
  Bar: radius=[4,4,0,0]
  Tooltip: contentStyle backgroundColor: {c['surface']}, border: {c['border']}, color: {c['text']}
  Legend: only when series > 1; small, muted
  No 3D, no shadows, no animations beyond default Recharts ease
"""


def base_stylesheet() -> str:
    """Tiny CSS reset + base body styles for the iframe sandbox."""
    c = ORIGIN_TOKENS["color"]
    t = ORIGIN_TOKENS["type"]
    return f"""\
html, body {{
  margin: 0;
  background: {c['bg']};
  color: {c['text']};
  font-family: {t['family']};
  font-size: 13px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}}
* {{ box-sizing: border-box; }}
.tabular-nums {{ font-variant-numeric: tabular-nums; }}
"""

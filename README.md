# origin-genviz

Stdio MCP proxy that sits in front of the **origin-staging** MCP server.
Every tool from origin-staging is re-exposed verbatim. After each call,
the raw result is shown to a Cerebras-backed agent (default
`zai-glm-4.7`, temp 0.2). When the agent decides a chart, table, or
KPI card would actually help, it returns a self-contained HTML widget
styled with the Origin design system, which the proxy attaches to the
response as an MCP **`ui://`** embedded resource (MCP App UI / `mcp-ui`).

```
client ──tools/call──▶ origin-genviz ──tools/call──▶ origin-staging
                              ▲                              │
                              │                              ▼
                              └── + ui:// resource ◀── viz agent (Cerebras)
```

## Install

```bash
uv sync                    # creates .venv, installs deps
# or: pip install -e .
```

## Auth

origin-genviz handles its own OAuth against the upstream — no dependency
on Claude Code's auth state. On first run you log in interactively; after
that the proxy refreshes tokens automatically.

```bash
uv run origin-genviz login    # opens browser; one-shot OAuth flow
uv run origin-genviz status   # shows whether tokens are present
uv run origin-genviz logout   # forget tokens
uv run origin-genviz          # serve (default subcommand)
```

The flow uses RFC 8414 discovery + RFC 7591 dynamic client registration
+ authorization code with PKCE. Tokens persist to
`$XDG_CONFIG_HOME/origin-genviz/credentials.json` (mode 0600). The MCP
SDK's `OAuthClientProvider` plugs into the streamable-HTTP transport as
an httpx Auth and refreshes the access token transparently mid-session.

If refresh ever truly fails (refresh-token rotation lost, server-side
revocation), the proxy returns a JSON-RPC error explicitly telling you
to run `origin-genviz login`.

To bypass OAuth entirely (e.g. CI), set `ORIGIN_STAGING_TOKEN=<bearer>`
and the proxy will use that as a static `Authorization` header.

## Configure

Copy `.env.example` and set at least `CEREBRAS_API_KEY`. Then run
`uv run origin-genviz login` once to authenticate the upstream.

## Run

```bash
CEREBRAS_API_KEY=csk-... uv run origin-genviz
```

It speaks MCP over stdio — connect any MCP client to the process.

## Wire it into Claude Code

```bash
# 1. authenticate the upstream once
uv --directory /home/depmod/code/sandpit/origin-genviz run origin-genviz login

# 2. register the proxy with Claude Code
claude mcp add origin-genviz \
  --env CEREBRAS_API_KEY=csk-... \
  -- uv --directory /home/depmod/code/sandpit/origin-genviz run origin-genviz
```

origin-genviz no longer needs origin-staging configured in Claude Code —
it has its own OAuth state.

## Configuration reference

| env var                     | default                                  | purpose                                              |
| --------------------------- | ---------------------------------------- | ---------------------------------------------------- |
| `CEREBRAS_API_KEY`          | —                                        | Cerebras key. Without it, proxy is a passthrough.    |
| `CEREBRAS_MODEL`            | `zai-glm-4.7`                            | Cerebras model id.                                   |
| `CEREBRAS_TEMPERATURE`      | `0.2`                                    | Sampling temperature.                                |
| `CEREBRAS_BASE_URL`         | `https://api.cerebras.ai/v1`             | OpenAI-compatible endpoint.                          |
| `ORIGIN_STAGING_URL`        | `https://mcp.staging.originhq.com/mcp`   | Upstream MCP URL.                                    |
| `ORIGIN_STAGING_SERVER_NAME`| `origin-staging`                         | `serverName` to match in credentials store.          |
| `ORIGIN_STAGING_TOKEN`      | —                                        | Static bearer override (skips OAuth entirely).       |
| `ORIGIN_GENVIZ_TOKEN_PATH`  | `$XDG_CONFIG_HOME/origin-genviz/credentials.json` | Where this proxy stores its own OAuth tokens. |
| `ORIGIN_GENVIZ_OAUTH_PORT`  | `53217`                                  | Local port for the OAuth callback during login.      |
| `ORIGIN_GENVIZ_OAUTH_TIMEOUT_S` | `300`                                | How long `login` waits for the browser flow.         |
| `UPSTREAM_TIMEOUT_S`        | `60`                                     | Per-call HTTP timeout to upstream.                   |
| `AGENT_TIMEOUT_S`           | `30`                                     | Hard cap on the viz agent.                           |
| `AGENT_MAX_INPUT_CHARS`     | `60000`                                  | Truncate large tool results before sending to LLM.   |
| `ORIGIN_GENVIZ_LOG`         | `INFO`                                   | Python log level.                                    |

## Visualization rules

The agent is instructed to **only** visualize when it adds clarity:

- visualize: tabular / time-series / categorical / numeric comparisons / KPI-shaped records
- pass through: simple acks, freeform prose, errors, trivially small payloads

Output is always strict JSON (`visualize` / `title` / `html` / `rationale`).
Any agent failure (timeout, malformed JSON, network) is non-fatal — the
raw result is returned unchanged.

Generated HTML must be **fully self-contained**: inline CSS, no CDN
scripts, no external fonts. Charts are hand-written SVG. The Origin
design tokens are injected into every prompt and re-emitted as CSS
variables in the widget.

To re-skin: edit `src/origin_genviz/design_tokens.py`. Changes take
effect on the next tool call.

The canonical Origin design system reference lives in `docs/origin-design/`:

```
docs/origin-design/
├── README.md                 ← full skill spec (voice, palette, components)
├── colors_and_type.css       ← canonical token CSS (source of truth)
└── assets/
    └── logo-origin-wordmark.svg
```

`design_tokens.py` is kept in sync with `colors_and_type.css`. If you
update one, update the other.

## Layout

```
src/origin_genviz/
├── __main__.py        argparse: serve (default) | login | logout | status
├── server.py          lowlevel MCP server, list_tools/call_tool handlers
├── upstream.py        streamable-http client to origin-staging
├── oauth.py           FileTokenStorage + OAuthClientProvider + login flow
├── viz_agent.py       Cerebras call + JSON parse
├── design_tokens.py   Origin palette, typography, Tailwind config
└── config.py          env-driven Config

assets/
└── logo-origin-wordmark.svg

docs/origin-design/    canonical design system reference
├── README.md
├── colors_and_type.css
└── assets/logo-origin-wordmark.svg
```

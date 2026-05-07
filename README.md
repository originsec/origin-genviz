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

The proxy reads the **origin-staging** OAuth bearer from
`~/.claude/.credentials.json` (the Claude Code credential store). If the
access token is expired, it tries the OAuth refresh-token grant against
the auth server discovered in that same file (`mcpOAuth.*.discoveryState.authorizationServerUrl`).
The refreshed token is held **in memory only** — we don't write back to
the Claude store, to avoid races with Claude Code's own refresh logic.

If both the access token AND the refresh token are stale (refresh tokens
rotate; once Claude Code has used them, the old one is invalid), you'll
see a clear error. Fix it by reconnecting the upstream MCP in Claude
Code (which will reset both tokens), or by exporting `ORIGIN_STAGING_TOKEN=<fresh-bearer>`.

## Configure

Copy `.env.example` and set at least `CEREBRAS_API_KEY`. Token resolution
order (no manual copy needed if you already auth'd origin-staging in Claude Code):

1. `ORIGIN_STAGING_TOKEN` env var
2. `~/.claude/.credentials.json` → `mcpOAuth["origin-staging|*"].accessToken`

Re-read on every call, so refreshes via `claude mcp` flow through without
restarting the proxy.

## Run

```bash
CEREBRAS_API_KEY=csk-... uv run origin-genviz
```

It speaks MCP over stdio — connect any MCP client to the process.

## Wire it into Claude Code

```bash
claude mcp add origin-genviz \
  --env CEREBRAS_API_KEY=csk-... \
  -- uv --directory /home/depmod/code/sandpit/origin-genviz run origin-genviz
```

(Then either disable the original `origin-staging` entry, or keep both —
the proxy doesn't try to claim that name.)

## Configuration reference

| env var                     | default                                  | purpose                                              |
| --------------------------- | ---------------------------------------- | ---------------------------------------------------- |
| `CEREBRAS_API_KEY`          | —                                        | Cerebras key. Without it, proxy is a passthrough.    |
| `CEREBRAS_MODEL`            | `zai-glm-4.7`                            | Cerebras model id.                                   |
| `CEREBRAS_TEMPERATURE`      | `0.2`                                    | Sampling temperature.                                |
| `CEREBRAS_BASE_URL`         | `https://api.cerebras.ai/v1`             | OpenAI-compatible endpoint.                          |
| `ORIGIN_STAGING_URL`        | `https://mcp.staging.originhq.com/mcp`   | Upstream MCP URL.                                    |
| `ORIGIN_STAGING_SERVER_NAME`| `origin-staging`                         | `serverName` to match in credentials store.          |
| `ORIGIN_STAGING_TOKEN`      | —                                        | Static bearer override (skips credentials lookup).   |
| `CLAUDE_CREDENTIALS_PATH`   | `~/.claude/.credentials.json`            | Where the OAuth store lives.                         |
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

## Layout

```
src/origin_genviz/
├── __main__.py        entrypoint
├── server.py          lowlevel MCP server, list_tools/call_tool handlers
├── upstream.py        streamable-http client to origin-staging
├── auth.py            reads ~/.claude/.credentials.json
├── viz_agent.py       Cerebras call + JSON parse
├── design_tokens.py   Origin palette, typography, base stylesheet
└── config.py          env-driven Config
```

# origin-genviz

MCP App that sits in front of the **origin-staging** MCP server. Every
upstream tool is re-exposed verbatim. After each call, the raw result is
shown to a Cerebras-backed agent (default `zai-glm-4.7`, temp 0.2). When
the agent decides a chart, table, or KPI card would actually help, it
returns a self-contained HTML widget styled with the Origin design
system. The widget is served to the host using the **MCP Apps SDK**
(`@modelcontextprotocol/ext-apps`) — declared with a proper CSP so the
CDN scripts (Recharts, Tailwind, Google Fonts) load reliably across
hosts (Claude Desktop, basic-host, etc).

The widget is also exposed via the **OpenAI Apps SDK** template
contract: every tool is annotated with `_meta["openai/outputTemplate"]`
pointing at a `text/html+skybridge` resource, and ChatGPT inline-renders
that template (reading the per-call HTML out of the same `_meta` payload).
Hosts that don't speak the OpenAI Apps SDK ignore the extra meta key.

Two processes:

```
host ──HTTP/MCP──▶ node-app  (MCP Apps wrapper, HTTP)
                      │
                      └─stdio MCP─▶ src/origin_genviz  (Python: OAuth + viz agent)
                                              │
                                              └─HTTP/MCP─▶ origin-staging
```

The Python proxy still owns OAuth against origin-staging and the
Cerebras viz call. The Node wrapper exposes the MCP App over streamable
HTTP, forwards tools, lifts the agent-generated HTML out of the
`_meta` sidechannel on each tool result, and renders it inside the
viewer resource (a sandboxed iframe with the right CSP).

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
# install Node deps once
cd node-app && npm install && cd ..

# serve the MCP App over streamable HTTP at /mcp
CEREBRAS_API_KEY=csk-... npm --prefix node-app start
# => http://127.0.0.1:3001/mcp
```

The Node process auto-spawns the Python proxy as a stdio child and
inherits env, so `CEREBRAS_API_KEY` and the OAuth tokens just flow
through. To run Python directly without the App layer (debugging, or
old mcp-ui clients), `uv run origin-genviz` still works — it now emits
the widget HTML on `result._meta["io.originhq/genviz"]` instead of as
an embedded `ui://` resource.

| env var (Node)         | default           | purpose                                         |
| ---------------------- | ----------------- | ----------------------------------------------- |
| `PORT`                 | `3001`            | HTTP port for `/mcp`.                           |
| `HOST`                 | `127.0.0.1`       | Bind address. Set `0.0.0.0` to expose on LAN.   |
| `GENVIZ_PYTHON_CMD`    | `uv`              | Command used to spawn the Python child.         |
| `GENVIZ_PYTHON_ARGS`   | `run origin-genviz` | Args for the Python child.                    |
| `GENVIZ_PYTHON_CWD`    | repo root         | cwd for the Python child.                       |

## Wire it into a host

```bash
# 1. authenticate the upstream once (Python side, one-shot OAuth)
uv run origin-genviz login

# 2. start the MCP App
CEREBRAS_API_KEY=csk-... npm --prefix node-app start

# 3. point your host at http://127.0.0.1:3001/mcp
```

For Claude Code:

```bash
claude mcp add --transport http origin-genviz http://127.0.0.1:3001/mcp
```

origin-genviz handles its own upstream OAuth — origin-staging does not
need to be configured in the host.

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
| `ORIGIN_GENVIZ_VIZ_ALLOW`   | (empty = all)                            | Comma-separated tool names eligible for viz. Default: all. |
| `ORIGIN_GENVIZ_VIZ_DENY`    | (empty)                                  | Comma-separated tool names that NEVER go through the agent (e.g. schema-style reference dumps). |
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

Generated HTML is React + Tailwind + Recharts loaded from CDN, plus
inline `<style>` and inline data. The viewer's CSP whitelists the CDN
origins (see `node-app/server.ts` → `WIDGET_RESOURCE_DOMAINS`); add to
that list if you change the prompt to use a different CDN.

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
node-app/                 MCP Apps wrapper (TypeScript, HTTP)
├── main.ts               streamable-HTTP entry point
├── server.ts             lowlevel MCP server: forwards tools, attaches viewer URI + CSP
├── upstream.ts           MCP stdio client that spawns the Python proxy
└── viewer.html           sandboxed viewer that srcdoc-renders the widget HTML

src/origin_genviz/        Python upstream proxy (stdio MCP)
├── __main__.py        argparse: serve (default) | login | logout | status
├── server.py          lowlevel MCP server; emits widget HTML on result._meta
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

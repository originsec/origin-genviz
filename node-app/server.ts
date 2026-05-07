/**
 * Lowlevel MCP server that re-exposes every upstream origin-staging tool
 * verbatim and embeds the agent-generated widget HTML as an MCP-UI
 * `type: "resource"` content block on each call's result.
 *
 * - Upstream JSON-Schemas pass through unchanged (no Zod conversion).
 * - On call: forward to Python, lift the widget HTML out of the result's
 *   `_meta` sidechannel, and append a `ui://origin-genviz/result/<id>.html`
 *   embedded resource (mime `text/html`, inline `text`) to the content
 *   array. The same HTML is also stashed in-memory keyed by URI so hosts
 *   that fetch via `readResource` instead of consuming inline `text`
 *   still get the widget.
 * - The `_meta` sidechannel is preserved alongside, for any host that
 *   speaks the MCP Apps SDK shape.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  ListResourcesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
  type CallToolResult,
  type Tool,
} from "@modelcontextprotocol/sdk/types.js";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Upstream, VIZ_META_KEY, type VizPayload } from "./upstream.js";

const SERVER_NAME = "origin-genviz";
const SERVER_VERSION = "0.2.0";

const VIZ_URI_PREFIX = "ui://origin-genviz/result/";

// Goose persists per-tool resource-URI mappings across reconnects. Older
// versions of this server tagged tools with this URI, so goose still calls
// readResource for it on every tool result. We dynamically serve the most
// recent viz under this URI so those stale references render correctly.
const LEGACY_VIEWER_URI = "ui://origin-genviz/viewer.html";

// OpenAI Apps SDK widget template. Annotated on every tool via
// `_meta["openai/outputTemplate"]`. ChatGPT loads this resource into a
// sandboxed iframe, exposes the tool result as `window.openai.toolOutput`,
// and emits `openai:set_globals` when the result is ready. The template
// reads `_meta["io.originhq/genviz"].html` and renders the agent-generated
// widget inside an inner iframe.
const OPENAI_VIEWER_URI = "ui://origin-genviz/viewer-openai.html";
const OPENAI_TEMPLATE_MIME = "text/html+skybridge";
const OPENAI_OUTPUT_TEMPLATE_META = "openai/outputTemplate";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// dist/server.js → ../viewer-openai.html in the source tree.
const OPENAI_VIEWER_HTML_CANDIDATES = [
  path.resolve(__dirname, "viewer-openai.html"),
  path.resolve(__dirname, "..", "viewer-openai.html"),
];

function loadOpenAIViewerHtml(): string {
  for (const p of OPENAI_VIEWER_HTML_CANDIDATES) {
    try {
      return readFileSync(p, "utf-8");
    } catch {
      /* try next */
    }
  }
  throw new Error(
    `viewer-openai.html not found in any of: ${OPENAI_VIEWER_HTML_CANDIDATES.join(", ")}`,
  );
}

const PLACEHOLDER_HTML = `<!doctype html><html><body style="margin:0;padding:24px;background:#FFF1E5;color:#66605C;font:12px/1.4 'Fira Code',monospace;letter-spacing:0.08em;text-transform:uppercase">origin · no visualization for this tool result</body></html>`;

// Cap retained widgets to avoid unbounded growth in long-lived servers.
const VIZ_CACHE_MAX = 64;

function cryptoRandomId(): string {
  return randomUUID().replace(/-/g, "").slice(0, 16);
}

class VizCache {
  private order: string[] = [];
  private map = new Map<string, string>();
  private latest: string | null = null;

  set(uri: string, html: string): void {
    if (this.map.has(uri)) {
      this.order = this.order.filter((u) => u !== uri);
    }
    this.map.set(uri, html);
    this.order.push(uri);
    this.latest = html;
    while (this.order.length > VIZ_CACHE_MAX) {
      const evict = this.order.shift();
      if (evict) this.map.delete(evict);
    }
  }

  get(uri: string): string | undefined {
    return this.map.get(uri);
  }

  getLatest(): string | null {
    return this.latest;
  }

  list(): string[] {
    return [...this.order];
  }
}

export function createServer(upstream: Upstream): Server {
  const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: {}, resources: {} } },
  );

  const cache = new VizCache();
  const openaiViewerHtml = loadOpenAIViewerHtml();

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const tools = await upstream.listTools();
    // Annotate every tool with the OpenAI Apps SDK template URI. ChatGPT
    // (and any future Apps-SDK host) will render that template iframe and
    // pass the tool result through `window.openai.toolOutput`. Other hosts
    // ignore unknown _meta keys, so this is purely additive.
    const annotated: Tool[] = tools.map((t) => {
      const existingMeta = (t as { _meta?: Record<string, unknown> })._meta ?? {};
      return {
        ...t,
        _meta: {
          ...existingMeta,
          [OPENAI_OUTPUT_TEMPLATE_META]: OPENAI_VIEWER_URI,
        },
      } as Tool;
    });
    return { tools: annotated };
  });

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const name = req.params.name;
    const args = (req.params.arguments ?? {}) as Record<string, unknown>;
    console.error(`[server] CallToolRequest: name=${name} args=${JSON.stringify(args)}`);

    let result: CallToolResult;
    let viz: VizPayload | null;
    try {
      ({ result, viz } = await upstream.callTool(name, args));
      console.error(`[server] upstream returned result, meta keys=`, Object.keys(result._meta ?? {}));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [
          {
            type: "text",
            text: `origin-genviz: upstream call failed: ${msg}`,
          },
        ],
        isError: true,
      } satisfies CallToolResult;
    }

    if (viz) {
      const vizUri = `${VIZ_URI_PREFIX}${cryptoRandomId()}.html`;
      cache.set(vizUri, viz.html);
      const existingContent = Array.isArray(result.content) ? result.content : [];
      result.content = [
        ...existingContent,
        {
          type: "resource",
          resource: {
            uri: vizUri,
            mimeType: "text/html",
            text: viz.html,
          },
        },
      ];
      const meta = (result._meta ?? {}) as Record<string, unknown>;
      result._meta = {
        ...meta,
        [VIZ_META_KEY]: {
          html: viz.html,
          title: viz.title ?? null,
          tool: viz.tool ?? name,
          rationale: viz.rationale ?? null,
        },
      };
      console.error(`[server] embedded viz resource: uri=${vizUri} html_length=${viz.html.length} title=${viz.title ?? 'null'}`);
    }

    console.error(`[server] returning result, content blocks=${result.content?.length ?? 0}, meta keys=`, Object.keys(result._meta ?? {}));

    return result;
  });

  server.setRequestHandler(ListResourcesRequestSchema, async () => {
    const uris = cache.list();
    console.error(`[server] ListResources: returning ${uris.length} cached viz resources + legacy viewer + openai template`);
    return {
      resources: [
        {
          uri: OPENAI_VIEWER_URI,
          name: "Origin viz (OpenAI Apps SDK template)",
          description:
            "Widget template for ChatGPT / OpenAI Apps SDK. Reads each call's HTML from window.openai.toolOutput._meta[\"io.originhq/genviz\"].html.",
          mimeType: OPENAI_TEMPLATE_MIME,
        },
        {
          uri: LEGACY_VIEWER_URI,
          name: "Origin viz (latest)",
          description:
            "Most recent agent-generated visualization. Served dynamically.",
          mimeType: "text/html",
        },
        ...uris.map((uri) => ({
          uri,
          name: "Origin viz",
          mimeType: "text/html",
        })),
      ],
    };
  });

  server.setRequestHandler(ReadResourceRequestSchema, async (req) => {
    const uri = req.params.uri;
    console.error(`[server] ReadResource: uri=${uri}`);

    // Per-call URI takes precedence — exact match.
    const exact = cache.get(uri);
    if (exact) {
      console.error(`[server] ReadResource: exact-match cache hit, html_length=${exact.length}`);
      return {
        contents: [{ uri, mimeType: "text/html", text: exact }],
      };
    }

    // OpenAI Apps SDK widget template — static, served verbatim.
    if (uri === OPENAI_VIEWER_URI) {
      console.error(`[server] ReadResource: serving OpenAI template html_length=${openaiViewerHtml.length}`);
      return {
        contents: [
          { uri, mimeType: OPENAI_TEMPLATE_MIME, text: openaiViewerHtml },
        ],
      };
    }

    // Legacy viewer URI (or any prior alias of it): serve the most recent
    // viz so goose's stale per-tool resource binding still renders.
    if (uri === LEGACY_VIEWER_URI) {
      const latest = cache.getLatest();
      const text = latest ?? PLACEHOLDER_HTML;
      console.error(`[server] ReadResource: legacy viewer URI, serving ${latest ? `latest viz html_length=${latest.length}` : "placeholder"}`);
      return {
        contents: [{ uri, mimeType: "text/html", text }],
      };
    }

    console.error(`[server] ReadResource: not found in cache (cache size=${cache.list().length})`);
    throw new Error(`Unknown resource: ${uri}`);
  });

  return server;
}

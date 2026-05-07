/**
 * Lowlevel MCP server that re-exposes every upstream origin-staging tool
 * verbatim and wires each one to the static viewer resource that renders
 * the agent-generated widget HTML for that call.
 *
 * - Upstream JSON-Schemas pass through unchanged (no Zod conversion).
 * - Each tool advertises `_meta.ui.resourceUri` pointing at the viewer.
 * - On call: forward to Python, lift the widget HTML out of the result's
 *   `_meta` sidechannel, and re-attach it under the same key on the
 *   outbound result so the viewer iframe can pick it up via
 *   `ontoolresult` and srcdoc-render it.
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
import { RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/server";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Upstream, VIZ_META_KEY, type VizPayload } from "./upstream.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const SERVER_NAME = "origin-genviz";
const SERVER_VERSION = "0.2.0";

const VIEWER_URI = "ui://origin-genviz/viewer.html";

// Origins the agent-generated widgets need to load. The widget runs inside
// a srcdoc iframe nested in the viewer, but srcdoc inherits the viewer's
// CSP — so these have to be declared on the viewer resource itself.
const WIDGET_RESOURCE_DOMAINS = [
  // Viewer itself loads the MCP Apps SDK from esm.sh.
  "https://esm.sh",
  // Origins the agent-generated widgets need at runtime.
  "https://unpkg.com",
  "https://cdn.tailwindcss.com",
  "https://fonts.googleapis.com",
  "https://fonts.gstatic.com",
];

let viewerHtmlCache: string | null = null;
async function loadViewerHtml(): Promise<string> {
  if (viewerHtmlCache !== null) return viewerHtmlCache;
  const p = path.join(__dirname, "viewer.html");
  viewerHtmlCache = await fs.readFile(p, "utf-8");
  return viewerHtmlCache;
}

function tagToolWithViewer(tool: Tool): Tool {
  // Both keys — `ui.resourceUri` (preferred) and the flat legacy key —
  // so old + new hosts both resolve the resource.
  const existingMeta = (tool._meta ?? {}) as Record<string, unknown>;
  const existingUi =
    typeof existingMeta.ui === "object" && existingMeta.ui !== null
      ? (existingMeta.ui as Record<string, unknown>)
      : {};
  return {
    ...tool,
    _meta: {
      ...existingMeta,
      ui: { ...existingUi, resourceUri: VIEWER_URI },
      "ui/resourceUri": VIEWER_URI,
    },
  };
}

export function createServer(upstream: Upstream): Server {
  const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: {}, resources: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const tools = await upstream.listTools();
    return { tools: tools.map(tagToolWithViewer) };
  });

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const name = req.params.name;
    const args = (req.params.arguments ?? {}) as Record<string, unknown>;

    let result: CallToolResult;
    let viz: VizPayload | null;
    try {
      ({ result, viz } = await upstream.callTool(name, args));
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
    }

    return result;
  });

  server.setRequestHandler(ListResourcesRequestSchema, async () => ({
    resources: [
      {
        uri: VIEWER_URI,
        name: "Origin Genviz Viewer",
        description:
          "Renders the agent-generated widget HTML for the most recent tool call.",
        mimeType: RESOURCE_MIME_TYPE,
      },
    ],
  }));

  server.setRequestHandler(ReadResourceRequestSchema, async (req) => {
    if (req.params.uri !== VIEWER_URI) {
      throw new Error(`Unknown resource: ${req.params.uri}`);
    }
    const html = await loadViewerHtml();
    return {
      contents: [
        {
          uri: VIEWER_URI,
          mimeType: RESOURCE_MIME_TYPE,
          text: html,
          _meta: {
            ui: {
              csp: {
                resourceDomains: WIDGET_RESOURCE_DOMAINS,
                connectDomains: [],
                frameDomains: [],
              },
            },
          },
        },
      ],
    };
  });

  return server;
}

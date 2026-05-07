/**
 * Streamable-HTTP entry point. Spawns the origin-genviz Python proxy
 * once and serves the wrapped MCP App at POST /mcp.
 *
 *   npm run start            # serves http://localhost:3001/mcp
 *   PORT=4000 npm run start  # custom port
 *
 * Env:
 *   PORT                   default 3001
 *   GENVIZ_PYTHON_CMD      default "uv"
 *   GENVIZ_PYTHON_ARGS     default "run origin-genviz" (space-separated)
 *   GENVIZ_PYTHON_CWD      default repo root (parent of node-app)
 *   plus any env vars the Python side reads (CEREBRAS_API_KEY, etc.) —
 *   the child inherits them.
 */
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import cors from "cors";
import type { Request, Response } from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Upstream } from "./upstream.js";
import { createServer } from "./server.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");

function buildUpstream(): Upstream {
  const command = process.env.GENVIZ_PYTHON_CMD ?? "uv";
  const argsStr = process.env.GENVIZ_PYTHON_ARGS ?? "run origin-genviz";
  const args = argsStr.split(/\s+/).filter(Boolean);
  const cwd = process.env.GENVIZ_PYTHON_CWD ?? REPO_ROOT;
  // StdioClientTransport drops env unless we hand it one explicitly. Pass
  // through the parent's env so OAuth tokens, CEREBRAS_API_KEY etc. all
  // reach the Python child.
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (typeof v === "string") env[k] = v;
  }
  return new Upstream({ command, args, cwd, env });
}

async function main(): Promise<void> {
  const port = Number.parseInt(process.env.PORT ?? "3001", 10);
  const upstream = buildUpstream();

  // Best-effort warm-up — surface auth / spawn errors at boot rather than
  // on the first tool call. Non-fatal if the upstream is briefly unhappy:
  // listTools will retry on the first real request.
  try {
    await upstream.start();
    const tools = await upstream.listTools();
    console.error(
      `[origin-genviz-app] upstream ready, ${tools.length} tools discovered`,
    );
  } catch (err) {
    console.error(
      `[origin-genviz-app] upstream warm-up failed (will retry on first request): ${
        err instanceof Error ? err.message : String(err)
      }`,
    );
  }

   // Bind to all interfaces so cloudflared / ngrok tunnels work without the
  // SDK's Host-header allowlist 403'ing them. Internal-only deployment —
  // exposure is gated by the tunnel, not by the bind address.
  const host = process.env.HOST ?? "0.0.0.0";
  const app = createMcpExpressApp({ host });
  app.use(cors());

  app.all("/mcp", async (req: Request, res: Response) => {
    const server = createServer(upstream);
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
    });

    res.on("close", () => {
      transport.close().catch(() => {});
      server.close().catch(() => {});
    });

    try {
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (err) {
      console.error("[origin-genviz-app] mcp request error:", err);
      if (!res.headersSent) {
        res.status(500).json({
          jsonrpc: "2.0",
          error: { code: -32603, message: "Internal server error" },
          id: null,
        });
      }
    }
  });

  const httpServer = app.listen(port, host, (err?: Error) => {
    if (err) {
      console.error("Failed to start server:", err);
      process.exit(1);
    }
    console.error(
      `[origin-genviz-app] listening on http://${host}:${port}/mcp`,
    );
  });

  const shutdown = async () => {
    console.error("[origin-genviz-app] shutting down");
    await upstream.close();
    httpServer.close(() => process.exit(0));
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

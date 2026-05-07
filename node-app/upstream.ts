/**
 * MCP client that spawns the origin-genviz Python proxy as a stdio
 * subprocess and forwards calls to it. The Python side handles upstream
 * OAuth + the Cerebras viz agent; we just shuttle requests/responses and
 * read the agent-generated widget HTML out of `result._meta`.
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type {
  CallToolResult,
  ListToolsResult,
  Tool,
} from "@modelcontextprotocol/sdk/types.js";

export const VIZ_META_KEY = "io.originhq/genviz";

export interface VizPayload {
  html: string;
  title?: string | null;
  rationale?: string | null;
  tool?: string;
}

export interface UpstreamConfig {
  command: string;
  args: string[];
  cwd?: string;
  env?: Record<string, string>;
}

export class Upstream {
  private client: Client;
  private transport: StdioClientTransport;
  private started = false;
  private startPromise?: Promise<void>;

  constructor(config: UpstreamConfig) {
    this.transport = new StdioClientTransport({
      command: config.command,
      args: config.args,
      cwd: config.cwd,
      env: config.env,
      // Inherit so Python's logging + interactive `login` prompts surface
      // in the operator's terminal.
      stderr: "inherit",
    });
    this.client = new Client(
      { name: "origin-genviz-app", version: "0.2.0" },
      { capabilities: {} },
    );
  }

  async start(): Promise<void> {
    if (this.started) return;
    if (!this.startPromise) {
      this.startPromise = this.client
        .connect(this.transport)
        .then(() => {
          this.started = true;
        })
        .catch((err) => {
          this.startPromise = undefined;
          throw err;
        });
    }
    await this.startPromise;
  }

  async listTools(): Promise<Tool[]> {
    await this.start();
    const tools: Tool[] = [];
    let cursor: string | undefined;
    do {
      const page: ListToolsResult = await this.client.listTools(
        cursor ? { cursor } : undefined,
      );
      tools.push(...page.tools);
      cursor = page.nextCursor;
    } while (cursor);
    return tools;
  }

  async callTool(
    name: string,
    args: Record<string, unknown>,
  ): Promise<{ result: CallToolResult; viz: VizPayload | null }> {
    await this.start();
    const result = (await this.client.callTool({
      name,
      arguments: args,
    })) as CallToolResult;

    const viz = extractViz(result);
    if (viz && result._meta) {
      // Strip the sidechannel before forwarding so the host never sees it.
      const { [VIZ_META_KEY]: _stripped, ...rest } = result._meta as Record<
        string,
        unknown
      >;
      result._meta = Object.keys(rest).length > 0 ? rest : undefined;
    }
    return { result, viz };
  }

  async close(): Promise<void> {
    if (this.started) {
      await this.client.close().catch(() => {});
    }
  }
}

function extractViz(result: CallToolResult): VizPayload | null {
  const meta = result._meta as Record<string, unknown> | undefined;
  if (!meta) return null;
  const raw = meta[VIZ_META_KEY];
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (typeof obj.html !== "string" || obj.html.length === 0) return null;
  return {
    html: obj.html,
    title: typeof obj.title === "string" ? obj.title : null,
    rationale: typeof obj.rationale === "string" ? obj.rationale : null,
    tool: typeof obj.tool === "string" ? obj.tool : undefined,
  };
}

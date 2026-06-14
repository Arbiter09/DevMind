#!/usr/bin/env node
/**
 * @devmind/github-mcp
 *
 * A Model Context Protocol (MCP) server that exposes GitHub PR tools to
 * AI agents. Communicates over stdio — launch with:
 *
 *   npx -y @devmind/github-mcp
 *
 * Required env: GITHUB_TOKEN
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import {
  getPrMetadata,
  getPrMetadataSchema,
  getPrDiff,
  getPrDiffSchema,
  listChangedFiles,
  listChangedFilesSchema,
} from "./tools/pr.js";

import {
  readFile,
  readFileSchema,
  getFileHistory,
  getFileHistorySchema,
} from "./tools/file.js";

import { postReviewComment, postReviewCommentSchema } from "./tools/review.js";

const server = new McpServer({
  name: "devmind-github",
  version: "1.0.0",
});

server.registerTool(
  "get_pr_metadata",
  {
    description:
      "Fetch PR title, author, labels, base branch, head SHA, and change stats (additions, deletions, changed_files).",
    inputSchema: getPrMetadataSchema,
  },
  async (args) => {
    const text = await getPrMetadata(args);
    return { content: [{ type: "text", text }] };
  }
);

server.registerTool(
  "get_pr_diff",
  {
    description: "Get the unified diff of all files changed in a pull request.",
    inputSchema: getPrDiffSchema,
  },
  async (args) => {
    const text = await getPrDiff(args);
    return { content: [{ type: "text", text }] };
  }
);

server.registerTool(
  "list_changed_files",
  {
    description:
      "List all files changed in a PR with their status (added/modified/removed/renamed) and line counts.",
    inputSchema: listChangedFilesSchema,
  },
  async (args) => {
    const text = await listChangedFiles(args);
    return { content: [{ type: "text", text }] };
  }
);

server.registerTool(
  "read_file",
  {
    description:
      "Read raw file content at a specific git ref (SHA or branch name). Content at a commit SHA is immutable — safe to cache aggressively.",
    inputSchema: readFileSchema,
  },
  async (args) => {
    const text = await readFile(args);
    return { content: [{ type: "text", text }] };
  }
);

server.registerTool(
  "get_file_history",
  {
    description:
      "Return recent commits that touched a file — useful for understanding ownership patterns and change frequency.",
    inputSchema: getFileHistorySchema,
  },
  async (args) => {
    const text = await getFileHistory(args);
    return { content: [{ type: "text", text }] };
  }
);

server.registerTool(
  "post_review_comment",
  {
    description:
      "Post a markdown-formatted review comment to the pull request on GitHub.",
    inputSchema: postReviewCommentSchema,
  },
  async (args) => {
    const text = await postReviewComment(args);
    return { content: [{ type: "text", text }] };
  }
);

async function main(): Promise<void> {
  if (!process.env.GITHUB_TOKEN) {
    process.stderr.write(
      "[devmind-github-mcp] ERROR: GITHUB_TOKEN is not set.\n" +
        "Export a GitHub Personal Access Token before running this server.\n"
    );
    process.exit(1);
  }

  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write("[devmind-github-mcp] Server running on stdio\n");
}

main().catch((err) => {
  process.stderr.write(`[devmind-github-mcp] Fatal error: ${err}\n`);
  process.exit(1);
});

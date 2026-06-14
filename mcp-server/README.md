# @devmind/github-mcp

GitHub MCP tools for autonomous PR review agents. Exposes six tools over the
[Model Context Protocol](https://modelcontextprotocol.io) (stdio transport) so
any MCP-compatible client — Cursor, Claude Desktop, or a custom agent — can
interact with GitHub pull requests without writing bespoke API glue code.

## Quick Start — one command

```bash
npx -y @devmind/github-mcp
```

Set `GITHUB_TOKEN` in the environment first:

```bash
export GITHUB_TOKEN=ghp_your_token_here
npx -y @devmind/github-mcp
```

## Cursor Setup

Add to your Cursor MCP config (`~/.cursor/mcp.json` or the workspace
`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "devmind-github": {
      "command": "npx",
      "args": ["-y", "@devmind/github-mcp"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

## Claude Desktop Setup

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "devmind-github": {
      "command": "npx",
      "args": ["-y", "@devmind/github-mcp"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `get_pr_metadata` | Fetch PR title, author, labels, base branch, head SHA, and change stats |
| `get_pr_diff` | Get the unified diff of all changed files |
| `list_changed_files` | List changed files with status and line counts |
| `read_file` | Read file content at a specific git ref (SHA or branch) |
| `get_file_history` | Recent commits that touched a file |
| `post_review_comment` | Post a markdown review comment to the PR |

### Tool schemas

#### get_pr_metadata
```json
{ "pr_number": 42, "repo": "owner/repo" }
```

#### get_pr_diff
```json
{ "pr_number": 42, "repo": "owner/repo" }
```

#### list_changed_files
```json
{ "pr_number": 42, "repo": "owner/repo" }
```

#### read_file
```json
{ "path": "src/api/users.py", "repo": "owner/repo", "ref": "abc123sha" }
```

#### get_file_history
```json
{ "path": "src/api/users.py", "repo": "owner/repo", "per_page": 10 }
```

#### post_review_comment
```json
{
  "pr_number": 42,
  "repo": "owner/repo",
  "body": "## Review\n\nFound a SQL injection risk on line 12...",
  "event": "REQUEST_CHANGES"
}
```

## GitHub Token Permissions

Generate a fine-grained token at
**GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**.

Required permissions:
- **Contents** — Read-only (for `read_file`, `get_file_history`)
- **Pull requests** — Read and write (for all PR tools + `post_review_comment`)
- **Metadata** — Read-only

## MCP Registry

This server is listed on [Smithery](https://smithery.ai) under `@devmind/github-mcp`.

## Development

```bash
git clone https://github.com/Arbiter09/DevMind
cd DevMind/mcp-server
npm install
npm run build      # compile TypeScript → dist/
npm run dev        # watch mode
GITHUB_TOKEN=ghp_... node dist/index.js   # run locally
```

## Publishing

```bash
npm login
npm publish --access public
```

## License

MIT

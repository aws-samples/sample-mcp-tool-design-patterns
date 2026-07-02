# V6: Strands Agent — Amazon Bedrock AgentCore Project

MCP server backed by a Strands agent. A single MCP tool is exposed to the client; behind it, the agent handles taxonomy lookup, synonym translation, grade interpretation, and multi-step reasoning using its own model (Anthropic's Claude Sonnet 4.6 via Amazon Bedrock).

## How This Was Created

Scaffolded with the AgentCore CLI:

```bash
agentcore create --project-name v6agentcore --name v6 --protocol MCP --memory none --skip-git --skip-python-setup --skip-install
```

Then adapted:
- Replaced the sample FastMCP tools with the Strands agent + MCP tool pattern
- Added `model/load.py` for Amazon Bedrock model configuration (Strands-native pattern)
- Copied `mock_bff_sqlite.py` and `anycompany_content.db` into the app directory

### Why MCP Protocol (Not HTTP)

The AgentCore CLI supports both `--protocol MCP` and `--protocol HTTP`. We use MCP because this project serves MCP tools directly.

**Note:** `agentcore dev` hardcodes port 8000 for MCP protocol servers. This is not configurable. Ensure port 8000 is available before starting the dev server.

Alternatively, scaffolding with `--protocol HTTP` and exposing `app = mcp.streamable_http_app()` gives flexible port assignment — but breaks `agentcore invoke` compatibility. We chose the standard MCP path for simplicity.

## Prerequisites

- Node.js 20+ (for AgentCore CLI)
- `@aws/agentcore` installed globally (`npm install -g @aws/agentcore`)
- AWS CLI configured with a profile that has Amazon Bedrock model access (us-west-2)
- Port 8000 available

## Running

```bash
cd v6
agentcore dev --skip-deploy --logs
```

MCP endpoint: `http://127.0.0.1:8000/mcp`

To verify the server is running:

```bash
agentcore dev list-tools
agentcore dev call-tool --tool agentic_search_content --input '{"question": "hello"}'
```

To install AWS CDK dependencies (needed only for cloud deploy, not local dev):

```bash
cd agentcore/cdk && npm install
```

Then you can drop `--skip-deploy` from the dev command.

## Shared Files

`mock_bff_sqlite.py` and `anycompany_content.db` are duplicated here from the repo root. If you modify the backend or seed data, update both copies.

## Files

| File | Purpose |
|------|---------|
| `app/v6/main.py` | MCP server with Strands agent behind a single tool |
| `app/v6/model/load.py` | Amazon Bedrock model configuration |
| `app/v6/mock_bff_sqlite.py` | Shared backend (copy from repo root) |
| `app/v6/anycompany_content.db` | SQLite database (copy from repo root) |
| `app/v6/pyproject.toml` | Python dependencies |
| `agentcore/agentcore.json` | AgentCore project config (single MCP runtime) |
| `agentcore/cdk/` | CDK stack for cloud deployment |

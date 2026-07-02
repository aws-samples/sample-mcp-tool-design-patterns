# MCP Tool Optimization Patterns

Poorly designed MCP tools cause LLMs to guess wrong parameter values, retry failed calls, and consume context that the model needs for reasoning. The most common fix — enriching tool descriptions with valid values and mappings — improves accuracy but adds token cost on every call. Every approach to making MCP tools work better involves navigating this tension between giving the LLM enough guidance and keeping context lean.

This repo demonstrates the tradeoffs. Six versions of the same K-12 educational content search API, each applying a different design pattern to the MCP layer. Same backend, same test data — only the tool design changes. Comments in the code discuss each approach in more detail.

## Choosing a Pattern

Each version represents an independent design choice with its own tradeoffs. Pick the one that fits your use case — they are not a required progression.

| Version | Approach | Tradeoff |
|---------|----------|----------|
| **V1** | Raw API passthrough | Minimal effort, poor LLM accuracy |
| **V2** | Rich descriptions | High accuracy, larger tool definition |
| **V3** | Schema-enforced enums | Prevents invalid values, smaller definition than V2 |
| **V4** | Lazy-loaded taxonomy | Leanest baseline, extra round-trip |
| **V5** | LLM introspection | Expert interpretation of ambiguous queries, you pay for inference |
| **V6** | Agentic backend | Direct control and full encapsulation, highest infrastructure cost |

No version wins across all dimensions. The right choice depends on your field count, vocabulary stability, latency budget, and how much you need consistent behavior across different clients.

## Getting Started

### Prerequisites

- [Python 3.13+](https://www.python.org/downloads/)
- [uv](https://github.com/astral-sh/uv#installation) (Python package manager)
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with [Amazon Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) (V5 and V6 only)
- [Node.js 20+](https://nodejs.org/) (V6 only)
- [`@aws/agentcore` CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) — install with `npm install -g @aws/agentcore` (V6 only)
- An MCP client ([Kiro](https://kiro.dev/) — free tier available, Kiro IDE, Amazon Q CLI, etc.)

### Start the servers

All versions use streamable-http transport. Each version is a standalone Python MCP server that listens on its own port. Start V1–V5 with the launch script:

```bash
./scripts/start_all.sh
```

This runs each server in the background using `uv run`, which installs dependencies from `pyproject.toml` automatically on first run:

| Version | Port | Endpoint |
|---------|------|----------|
| V1 | 8001 | http://127.0.0.1:8001/mcp |
| V2 | 8002 | http://127.0.0.1:8002/mcp |
| V3 | 8003 | http://127.0.0.1:8003/mcp |
| V4 | 8004 | http://127.0.0.1:8004/mcp |
| V5 | 8005 | http://127.0.0.1:8005/mcp |

V6 runs separately via Amazon Bedrock AgentCore CLI (port 8000 must be available):

```bash
cd v6 && agentcore dev --skip-deploy --logs
```

Stop V1–V5:

```bash
./scripts/stop_all.sh
```

V6 stops with Ctrl+C in its terminal.

### Connect your MCP client

`setup_agents.py` creates a Kiro agent profile for each version in `~/.kiro/agents/`. Each profile points to one server's endpoint, so you can switch between versions without editing config files:

```bash
python scripts/setup_agents.py
```

Then swap between versions in Kiro:

```
/agent swap v1-passthrough
/agent swap v4-lazy
/agent swap v6-agent
```

Clear history between versions: `/clear`

> **Note:** `setup_agents.py`, `/agent swap`, and `/clear` are specific to Kiro CLI (current release). The generated agent profiles use the Kiro CLI agent format and are not compatible with the Kiro v3 preview. If you use Kiro IDE, the v3 preview, or a different MCP client, configure it manually to point at any server's endpoint:

```json
{
  "mcpServers": {
    "content-search": {
      "url": "http://127.0.0.1:8004/mcp"
    }
  }
}
```

## Test Queries

Now that you have the servers running and your MCP client connected, try these with each version and compare behavior:

1. `"Find me a quiz on fractions for my 7th graders"` — synonym mapping + grade interpretation
2. `"Do you have any lessons for teaching Spanish in middle school?"` — subject + grade range inference
3. `"I need TEKS-aligned content for kids working on dividing in middle school"` — multi-translation (synonym + standard + grade)
4. `"What types of content can I search for?"` — discovery / taxonomy
5. `"Can I get details on n-sc-1096?"` — resource detail retrieval

As you run each query, compare across versions:

- Whether the LLM picked the right filter values on the first call
- How many tool calls it took
- How much context the tool definition consumes

**Model switching:** Try `/model` in Kiro to switch between models and try the same queries. V5 and V6 produce consistent results regardless of client model. Earlier versions depend more on the client model's ability to interpret the tool descriptions.

Each version's source file opens with a comment header explaining its approach, the context tradeoff it makes, and what changed from the previous version. Read those headers alongside the code to understand what each version is doing and what to look for.

## Files

| File | Purpose |
|------|---------|
| `v1_passthrough.py` | Raw API fields, bare descriptions (anti-pattern baseline) |
| `v2_better_descriptions.py` | Rich docstring descriptions with valid values and synonyms |
| `v3_rethought_schema.py` | LLM-friendly names, Literal enums, layered tools |
| `v4_lazy_loading.py` | Minimal descriptions + on-demand taxonomy tool |
| `v5_llm_introspect.py` | Amazon Bedrock Converse call interprets queries before search |
| `v6/` | AgentCore project for V6 — Strands agent behind a single MCP tool (see `v6/README.md`) |
| `mock_bff_sqlite.py` | Shared backend — all versions call the same functions |
| `anycompany_content.db` | SQLite database (940 mock K-12 content records) |
| `seed_anycompany_content_sqlite.sql` | Seed script to rebuild the database |
| `scripts/setup_agents.py` | Generates Kiro agent configs for all versions |
| `scripts/start_all.sh` | Start V1–V5 in background |
| `scripts/stop_all.sh` | Stop V1–V5 |
| `pyproject.toml` | Python dependencies (used by `uv run`) |

**Note:** `mock_bff_sqlite.py` and `anycompany_content.db` are duplicated in `v6/app/v6/` for AgentCore compatibility. If you modify the backend or seed data, update both copies.

## AWS Services

- **[Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/)** — Converse API with Amazon Nova 2 Lite (V5 introspect) and Anthropic's Claude Sonnet 4.6 (V6 agent)
- **[Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)** — Hosts V6 locally during development and deploys to the cloud without managing infrastructure. AgentCore provides:
  - **[Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)** — Deploy and run MCP servers and agents as managed endpoints
  - **[Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)** — Semantic tool discovery across multiple MCP servers
  - **[Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html)** — Persistent context across sessions
  - **[CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)** — Local development with `agentcore dev`, scaffolding, and deployment (`npm install -g @aws/agentcore`)
- **[Strands Agents SDK](https://strandsagents.com/)** — Agent framework powering V6's internal reasoning loop

## Cleanup and Cost

**V1–V4** run locally with no AWS charges.

**V5 and V6** call Amazon Bedrock and incur per-request charges for model invocation. Stop the servers when not in use:

- V1–V5: `./scripts/stop_all.sh`
- V6: Ctrl-C the `agentcore dev` process

## License

This project is licensed under the MIT-0 License.

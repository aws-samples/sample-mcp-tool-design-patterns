# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#!/usr/bin/env python3
"""Generate Kiro agent configs for each MCP server version.

Creates 6 agent profiles in ~/.kiro/agents/ so you can switch between
versions with: /agent swap v1-passthrough

Each agent connects to a running MCP server via streamable-http.
Start servers first with ./start_all.sh (V1-V5) and agentcore dev (V6).

Usage:
    python setup_agents.py
"""

import json
import os

agents_dir = os.path.expanduser("~/.kiro/agents")
os.makedirs(agents_dir, exist_ok=True)

versions = [
    ("v1-passthrough", 8001, "V1: BFF fields with bare descriptions"),
    ("v2-descriptions", 8002, "V2: Rich descriptions"),
    ("v3-schema", 8003, "V3: LLM-friendly names + enums"),
    ("v4-lazy", 8004, "V4: Lazy loading taxonomy"),
    ("v5-introspect", 8005, "V5: LLM introspection"),
    ("v6-agent", 8000, "V6: Full Strands agent — single agentic tool"),
]

for name, port, desc in versions:
    agent = {
        "name": name,
        "description": desc,
        "prompt": None,
        "mcpServers": {name: {"url": f"http://127.0.0.1:{port}/mcp"}},
        "tools": ["*"],
        "toolAliases": {},
        "allowedTools": [],
        "resources": [],
        "hooks": {},
        "toolsSettings": {},
        "includeMcpJson": False,
        "model": None,
    }
    filepath = os.path.join(agents_dir, f"{name}.json")
    with open(filepath, "w") as f:
        json.dump(agent, f, indent=2)
    print(f"  Created {name} → http://127.0.0.1:{port}/mcp")

print(f"\nDone. 6 agents created in {agents_dir}")
print(f"\nUsage:")
print(
    f"  1. Start servers: ./start_all.sh (V1-V5) + cd v6 && agentcore dev --skip-deploy --logs (V6)"
)
print(f"  2. Swap agents:   /agent swap v1-passthrough")
print(f"  3. Clear history between versions: /clear")

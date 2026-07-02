#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Start V1-V5 MCP servers (background, streamable-http)
# V6 runs separately via: cd v6 && agentcore dev --skip-deploy --logs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p logs

echo "Starting V1-V5..."
uv run v1_passthrough.py >> logs/v1.log 2>&1 &
uv run v2_better_descriptions.py >> logs/v2.log 2>&1 &
uv run v3_rethought_schema.py >> logs/v3.log 2>&1 &
uv run v4_lazy_loading.py >> logs/v4.log 2>&1 &
uv run v5_llm_introspect.py >> logs/v5.log 2>&1 &

echo ""
echo "MCP servers running:"
echo "  V1: http://127.0.0.1:8001/mcp  (log: logs/v1.log)"
echo "  V2: http://127.0.0.1:8002/mcp  (log: logs/v2.log)"
echo "  V3: http://127.0.0.1:8003/mcp  (log: logs/v3.log)"
echo "  V4: http://127.0.0.1:8004/mcp  (log: logs/v4.log)"
echo "  V5: http://127.0.0.1:8005/mcp  (log: logs/v5.log)"
echo ""
echo "V6 (agentcore): cd v6 && agentcore dev --skip-deploy --logs"
echo ""
echo "Run ./scripts/stop_all.sh to stop V1-V5."

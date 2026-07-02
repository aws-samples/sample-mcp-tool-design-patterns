#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Stop V1-V5 MCP servers
# V6 (agentcore) is stopped with Ctrl+C in its terminal.

pkill -f "v1_passthrough.py" 2>/dev/null
pkill -f "v2_better_descriptions.py" 2>/dev/null
pkill -f "v3_rethought_schema.py" 2>/dev/null
pkill -f "v4_lazy_loading.py" 2>/dev/null
pkill -f "v5_llm_introspect.py" 2>/dev/null

wait 2>/dev/null
echo "V1-V5 stopped."

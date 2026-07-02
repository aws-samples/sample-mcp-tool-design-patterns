# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from strands.models.bedrock import BedrockModel


def load_model() -> BedrockModel:
    """Get Amazon Bedrock model client for the search agent.

    V6 uses a more capable model than V5's introspect tool because the agent
    performs full agentic reasoning — deciding which tools to call, when to
    broaden searches, and when to stop.
    """
    return BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-6", region_name="us-west-2"
    )

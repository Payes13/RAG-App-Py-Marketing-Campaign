#!/usr/bin/env python3
import aws_cdk as cdk
from cdk.marketing_ai_stack import MarketingAIStack
from cdk.pipeline_stack import PipelineStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

MarketingAIStack(app, "MarketingAIStack", env=env)
PipelineStack(app, "MarketingAIPipelineStack", env=env)

app.synth()

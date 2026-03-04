"""
CDK Pipeline Stack: CodePipeline with Source → Build → Staging → Approval → Production.
"""
from aws_cdk import Stack
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import pipelines
from constructs import Construct


class DeployStage(pipelines.Stage):
    """A CDK stage that deploys the MarketingAIStack."""

    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        from cdk.marketing_ai_stack import MarketingAIStack
        MarketingAIStack(self, "MarketingAIStack")


class PipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Source: CodeCommit repository
        repo = codecommit.Repository.from_repository_name(
            self, "MarketingAIRepo", "marketing-ai"
        )

        # CDK Pipeline
        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="marketing-ai-pipeline",
            synth=pipelines.ShellStep(
                "Synth",
                input=pipelines.CodePipelineSource.code_commit(repo, "main"),
                commands=[
                    "pip install -r requirements.txt",
                    "pip install -r requirements-dev.txt",
                    "npm install -g aws-cdk",
                    "pytest tests/ --tb=short",
                    "cdk synth",
                ],
                primary_output_directory="cdk.out",
            ),
            code_build_defaults=pipelines.CodeBuildOptions(
                build_environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                )
            ),
        )

        # Deploy to Staging
        staging_stage = pipeline.add_stage(
            DeployStage(self, "Staging"),
        )

        # Manual approval gate before Production
        pipeline.add_stage(
            DeployStage(self, "Production"),
            pre=[
                pipelines.ManualApprovalStep("PromoteToProduction"),
            ],
        )

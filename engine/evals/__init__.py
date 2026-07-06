"""solidifai model-quality eval harness (dev infrastructure).

Runs golden briefs through a headless agent against a provisioned temp
workspace, then grades the produced ARTIFACTS (never the transcript) with a
fresh engine session and a versioned VLM rubric judge.

Repo-only: this package is deliberately absent from the wheel's package list
(`[tool.hatch.build.targets.wheel]` in pyproject.toml), so it is never shipped
in the app binary or provisioned into user workspaces.
"""

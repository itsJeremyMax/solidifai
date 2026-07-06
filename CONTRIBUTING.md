# Contributing to solidifai

Thanks for your interest. solidifai is an early MVP, and contributions, issues, and ideas are
welcome. Please open an issue to discuss larger changes before sending a PR.

## Project layout

solidifai is one repo with three parts (see the README for the full map):

- `src/`: React + TypeScript frontend (Vite, Tailwind v4).
- `src-tauri/`: the Rust/Tauri shell (process supervision, IPC, filesystem, PTY).
- `engine/`: the Python CAD engine (build123d/OpenCascade) and its MCP server.

## Prerequisites

- Node 22+ and [pnpm](https://pnpm.io) 10+
- Rust (stable) and the platform toolchain Tauri needs (see the
  [Tauri prerequisites](https://tauri.app/start/prerequisites/): Xcode Command Line Tools
  on macOS, webkit2gtk and friends on Linux, MSVC on Windows)
- [uv](https://docs.astral.sh/uv/) for the Python engine

## Setup

```sh
pnpm install                 # frontend deps + git hooks (the prepare script wires .githooks)
cd engine && uv sync         # engine venv
```

## The gates

CI runs the same checks on every pull request; run them locally before pushing. A change is
ready when all three stacks are green.

Frontend:

```sh
pnpm exec tsc --noEmit       # typecheck
pnpm exec eslint .           # lint (react-hooks rules incl. exhaustive-deps are errors)
pnpm exec prettier --check . # format
pnpm exec vitest run         # tests
```

Engine:

```sh
cd engine
uv run ruff check .          # lint
uv run ruff format --check . # format
uv run mypy solidifai_engine solidifai_mcp solidifai   # types
uv run pytest                # tests
```

On Linux, the engine tests need headless GL: install Mesa (`libgl1-mesa-dev`,
`libglu1-mesa`) and run pytest under a virtual display, `xvfb-run -a uv run pytest`,
as CI does.

Shell:

```sh
cargo fmt   --manifest-path src-tauri/Cargo.toml --check
cargo clippy --manifest-path src-tauri/Cargo.toml --workspace --all-targets -- -D warnings
cargo test  --manifest-path src-tauri/Cargo.toml --workspace
```

`pnpm exec prettier --write .`, `uv run ruff format .`, and `cargo fmt` apply the
formatting for you.

### Pre-commit hook

`pnpm install` points git at `.githooks`. The `pre-commit` hook runs format + lint on the
files you staged (fast; no test suites), and `commit-msg` enforces commit style. Each block
skips gracefully if a toolchain is not installed, and CI is the backstop.

## Commits

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): summary`, where type is one of build, chore, ci, docs, feat, fix, perf,
refactor, revert, style, test. This is enforced locally (`commit-msg` hook) and in CI.

Keep user-facing copy (UI, errors, toasts, MCP text) plainly written, and avoid em dashes.
Comments should explain the why for the next reader, not narrate every line.

## Pull requests

1. Branch off `main`.
2. Make the change with tests, and keep all three gates green.
3. Use Conventional Commit messages.
4. Open a PR and describe the change and how you verified it. Link the issue if there is one.

## Security

Please report vulnerabilities privately. See [SECURITY.md](SECURITY.md).

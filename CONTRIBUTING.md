# Contributing to Iroko / OMNiBot 2000

Thanks for your interest! This is a personal robotics project, but issues and
pull requests are welcome.

## Ground rules

- **Never commit directly to `main`.** It is protected — work on a feature
  branch and open a Pull Request.
- **Conventional Commits** are enforced (via Commitizen). Format:
  `type(scope): description` — e.g. `feat(chat): add streaming endpoint`.
  Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`.
- Keep the commit title **≤ 72 characters** (Commitizen rejects longer titles).

## Development setup

This project uses [`uv`](https://docs.astral.sh/uv/) (workspace layout) and
[`just`](https://github.com/casey/just) as the task runner. Python 3.12.

```bash
just setup        # uv sync + pre-commit install + secrets baseline
```

## Before you open a PR

Run the same quality gate CI runs:

```bash
just check        # all pre-commit hooks: ruff, ruff-format, mypy, bandit, ...
just test         # pytest
```

A mergeable PR must satisfy:

- `ruff check .` and `ruff format --check .` pass with zero warnings.
- `mypy server/src robot/src` reports zero errors.
- Tests pass; coverage stays at or above 80%.
- Type hints on every function signature; Google-style docstrings on public APIs.
- No `print()` (use `logging`), no bare `except`, no hardcoded secrets/paths.

## Branch workflow

```bash
git switch -c feat/my-change
# ... work, commit with conventional messages ...
git push -u origin feat/my-change
# open a PR against main
```

## Architecture boundary (please respect)

The **server** is a generic audio/text API — it does not know a robot exists.
The **robot** is a generic client — it does not know about STT/LLM/TTS.
They share only the documented API contract. Do not break this separation.

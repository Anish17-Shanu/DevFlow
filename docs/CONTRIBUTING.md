# Contributing

## Development flow

1. Create a virtualenv and install `pip install -r backend/requirements-dev.txt`.
2. Install frontend dependencies with `npm ci` inside `frontend`.
3. Run `ruff check backend migrations` and `ruff format --check backend migrations`.
4. Run `python -m pytest --cov=backend`.
5. Run `npm run test:coverage` and `npm run build` inside `frontend`.
6. Run `npm run test:e2e` for changes that touch the UI or the execution flow.
7. Update docs when API, deployment, or operational behavior changes.

PostgreSQL integration tests run when `DEVFLOW_TEST_POSTGRES_URL` is set:

```bash
export DEVFLOW_TEST_POSTGRES_URL=postgresql+asyncpg://devflow:devflow@127.0.0.1:5432/devflow
python -m pytest
```

## Dependency lockfiles

Runtime and development dependencies are declared in `backend/requirements.in` and `backend/requirements-dev.in`. Lockfiles with hashes are committed:

```bash
cd backend
pip-compile --generate-hashes -o requirements.lock requirements.in
pip-compile --generate-hashes -o requirements-dev.lock requirements-dev.in
```

`requirements.txt` and `requirements-dev.txt` remain human-readable pinned files for local installs. CI installs with `--require-hashes` from the lockfiles. Dependabot opens weekly update PRs; regenerate the locks in the same PR.

## Coding expectations

- Keep backend changes consistent with the route → controller → service → repository structure.
- Prefer explicit validation and predictable state transitions over hidden magic.
- Keep deployment and operational documentation aligned with code changes.
- Add or update tests when changing queue, execution, auth, or health behavior.
- Do not execute untrusted task configuration as code; use the handler registry.
- Never log secrets, API keys, or task payloads that contain secret values.

## Pull request checklist

- Tests, lint, formatting, and frontend build pass.
- PostgreSQL migration up/down/up verified for schema changes.
- API documentation regenerated for route or schema changes.
- `ROADMAP.md` updated with status and evidence.
- Environment variable changes reflected in `.env.example`.
- Deployment and operations docs match runtime behavior.

# Contributing

## Development Flow

1. Install backend dependencies with `pip install -r backend/requirements.txt`.
2. Install frontend dependencies with `npm install` inside `frontend`.
3. Run `python -m pytest`.
4. Run `npm run build`.
5. Update docs when API, deployment, or operational behavior changes.

## Coding Expectations

- Keep backend changes consistent with the service-controller-route structure.
- Prefer explicit validation and predictable state transitions over hidden magic.
- Keep deployment and operational documentation aligned with code changes.
- Add or update tests when changing queue, execution, or health behavior.

## Pull Request Checklist

- tests pass
- frontend build passes
- deployment docs still match runtime behavior
- environment variable changes are reflected in `.env.example`

## Summary

<!-- What changed and why? Link the roadmap ID or issue. -->

## Type of change

- [ ] Bug fix
- [ ] Feature
- [ ] Reliability / performance
- [ ] Security
- [ ] Documentation
- [ ] CI / infrastructure
- [ ] Dependency update

## Verification

<!-- Paste commands and results, not just claims. -->

- [ ] `ruff check backend migrations`
- [ ] `ruff format --check backend migrations`
- [ ] `python -m pytest`
- [ ] `python scripts/generate_api_docs.py --check` (if API changed)
- [ ] `cd frontend && npm run test:coverage && npm run build`
- [ ] `cd frontend && npm run test:e2e` (if UI or API flow changed)
- [ ] PostgreSQL migration up/down/up (if schema changed)

## Production checklist

- [ ] `.env.example` updated for new or changed configuration.
- [ ] `ROADMAP.md` status/evidence updated.
- [ ] `docs/API.md` regenerated if routes or schemas changed.
- [ ] No secrets, credentials, or personal data added.
- [ ] Destructive operations documented and reversible.

## Screenshots / evidence

<!-- UI changes: include 360 px and 1440 px captures. -->

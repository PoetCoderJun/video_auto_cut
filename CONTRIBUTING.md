# Contributing

Thanks for taking the time to improve PoetCut.

## Development Setup

1. Install Python dependencies with `python -m pip install -r requirements.txt`.
2. Install frontend dependencies with `npm --prefix web_frontend install`.
3. Copy `.env.example` to `.env` and configure your own local credentials.
4. Start the local stack with `./scripts/start_web_mvp.sh debug`.

## Pull Request Expectations

- Keep changes focused on one user-visible behavior or one maintenance concern.
- Do not commit generated media, local databases, `workdir*/`, `.next/`, `.omx/`,
  `.claude/`, `.env`, or credentials.
- Add or update tests for backend contracts, prompt behavior, render contracts,
  and frontend state transitions when those areas change.
- Include the commands you ran and any manual verification that matters.

## Commercial Boundary

The open-source repository should stay usable for self-hosting, but production
PoetCut service credentials, customer data, analytics properties, payment setup,
and provider accounts must remain outside the repo.

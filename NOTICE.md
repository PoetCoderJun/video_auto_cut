# Notice

This repository is prepared as the open-source codebase for PoetCut, a Chinese
talking-head video editing product.

## License Scope

- Source code and documentation are licensed under `AGPL-3.0-or-later` unless a
  file states otherwise.
- Third-party packages keep their own licenses. Review dependency notices before
  shipping a public release or commercial distribution.
- The PoetCut name, logos, domains, hosted service, production infrastructure,
  deployment credentials, analytics properties, databases, customer data, and
  other business assets are not included in the open-source grant.

## Hosted Service Boundary

The public repository can be self-hosted with your own Turso/libsql database,
object storage, ASR provider, LLM provider, and auth secrets. The production
PoetCut online service remains a separate commercial deployment with private
environment variables, provider accounts, monitoring, operational data, and any
future paid-service integrations.

## Sensitive Data Policy

Do not commit `.env`, local sqlite/libsql replicas, `workdir*/` artifacts,
browser profiles, generated media, customer uploads, rendered exports, or local
agent state directories.

# Infrastructure Instructions

These rules apply to infrastructure owned by the whole deployment under `infra/**`. Configuration
that belongs only to the backend must stay with that application; shared edge, network,
deployment, and cross-service infrastructure belongs here or in the root Docker Compose files.

## Edge And Network Boundaries

- Keep nginx as the public edge for TLS, public domains, `/api/*`, and the public MinIO object
  endpoint. Do not add sitemap or robots edge locations: discovery
  routes are deliberately absent. VPN-only internal panels must remain bound to `VPN_BIND_ADDRESS`.
- Keep security headers and CSP at nginx. Add only the exact asset, external origin, Swagger/UI,
  upload-preview, or MinIO source required; do not use wildcard origins or broaden inline script or
  style allowances.
- Coarse anonymous public rate limiting belongs at nginx. Add backend rate limiting only for an
  explicitly designed identity-aware or business quota keyed by a user, API key, tenant,
  or subscription.

## Container Security

- Do not add public service ports, `network_mode: host`, `privileged: true`, Docker socket mounts,
  broad `cap_add`, or root runtime users unless the task explicitly requires them and documents the
  security tradeoff.
- Keep backend, PostgreSQL, Valkey, MinIO, and internal panels on private networks with
  only the intended nginx or VPN-bound entrypoint exposed.

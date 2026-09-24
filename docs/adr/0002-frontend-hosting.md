# ADR 0002: Front-end hosting

- Status: Accepted
- Date: 2026-09-24

## Context

The web app is a Next.js (App Router) client for the API. Options for hosting on AWS:

1. **Static export on S3 + CloudFront**: `output: 'export'` produces plain HTML/JS. S3 stores it; CloudFront serves it with TLS and caching.
2. **Next.js server on ECS Fargate** (behind an ALB, optionally CloudFront): full Next.js features, including SSR, route handlers, middleware, and image optimization.

The app is interactive and user specific (chat, seller data), so server rendering adds little. All data comes from the FastAPI backend, which already owns auth and business logic. Cost matters: this project runs under a small monthly budget.

## Decision

Use static export, hosted on a private S3 bucket behind CloudFront (Origin Access Control). No Next.js server runs in production.

## Consequences

- Near-zero hosting cost and nothing to patch or scale; CloudFront handles caching and TLS.
- Not available: SSR, route handlers (`app/api`), middleware, server actions, and `next/image` optimization (images are served unoptimized).
- `NEXT_PUBLIC_*` values are inlined at build time, so each environment needs its own build.
- The browser calls the API directly, so the API must set CORS for the CloudFront origin.
- `trailingSlash: true` emits `path/index.html`; a small CloudFront Function will be needed to map `/path/` to `/path/index.html` with a private S3 origin.

## Revisit if

- A page needs server rendering for SEO or first-load performance.
- We need server-side secrets in the front end (for example a backend-for-frontend auth pattern).
- Build-per-environment becomes painful enough to justify runtime config.

# web

Next.js (App Router) front end, built as a static export (`out/`) for S3 + CloudFront.

```bash
cp .env.example .env.local
pnpm install
pnpm dev          # http://localhost:3000, needs the API running (`make up` at repo root)
pnpm lint && pnpm typecheck && pnpm build
```

`NEXT_PUBLIC_API_BASE_URL` is baked into the bundle at build time, so each environment needs its own build.

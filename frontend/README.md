# NFL Analytics frontend

React, TypeScript, React Router, and Vite. Use Node 22.

```sh
npm ci
npm run dev
npm test
npm run lint
npm run build
```

`VITE_API_BASE_URL` selects the Functions API at build time; use
`http://localhost:7071` in `.env.local` for development. An empty value uses
same-origin routing. All requests use `src/api.ts`; the dashboard shares its
team request through `TeamAnalyticsProvider`.

Routes: `/`, `/forecast`, and `/team/:teamCode`. Static Web Apps navigation
fallback lives in `public/staticwebapp.config.json`.

Ranking tests use Node's test runner and deterministic simulated data. See the
[root README](../README.md) for model validation, backend setup, and deployment.

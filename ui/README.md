# DocFlow UI

Angular 22 frontend for DocFlow (standalone components, signals, zoneless, chart.js).
Pages: **Pipeline**, **Companies** (+ detail), **Filing viewer**, **Review queue**, **Q&A**, **Evaluation**.
The API contract is mirrored from `../api/schemas.py` in `src/app/core/api.models.ts`.

## Develop

```bash
npm ci
npm start            # http://localhost:4200, proxies /api -> http://localhost:8000 (proxy.conf.json)
npm run build        # production build -> dist/ui/browser
```

## Quality

```bash
npm run lint         # angular-eslint (src + e2e)
npm run format       # prettier --write
npm run format:check
npm test -- --watch=false   # unit tests (Vitest via @angular/build:unit-test)
```

## End-to-end (Playwright)

```bash
npx playwright install chromium
```

| Mode                | Command                  | Notes                                                                      |
| ------------------- | ------------------------ | -------------------------------------------------------------------------- |
| Mocked (no backend) | `E2E_MOCK=1 npm run e2e` | `/api/**` is fulfilled from `e2e/fixtures/*.json` via `page.route`         |
| Real backend        | `npm run e2e`            | backend on :8000 in demo mode, UI on :4200; asserts structure, not numbers |

- `E2E_BASE_URL` – UI under test (default `http://localhost:4200`).
- `E2E_START_SERVER=1` – let Playwright start `npm start` itself.

PowerShell: `$env:E2E_MOCK='1'; $env:E2E_START_SERVER='1'; npm run e2e`.

## Docker

```bash
docker build -t docflow-ui .
docker run -p 8080:80 --network <compose-network> docflow-ui
```

nginx serves the SPA (with `index.html` fallback) and proxies `/api/` to `http://api:8000/api/`.

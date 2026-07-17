# Accounting Software Frontend

Vue 3 + Vite + TypeScript interface for creating income and expense
transactions.

Run these commands from the repository root:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Alternatively, enter the frontend directory first:

```bash
cd frontend
npm install
npm run dev
```

The development server runs at `http://127.0.0.1:8101`. When started with the
repository `start.sh`, it proxies `/api` requests to the FastAPI backend on the
internal loopback port `18101`.

## Test and build

```bash
npm test
npm run build
```

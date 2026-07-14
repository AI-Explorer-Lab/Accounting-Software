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

The development server runs at `http://127.0.0.1:5173` and proxies `/api`
requests to the FastAPI backend at `http://127.0.0.1:8000`.

## Test and build

```bash
npm test
npm run build
```

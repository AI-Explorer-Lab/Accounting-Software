# Accounting Software

The project has separate backend and frontend applications. Commands must be
run in the corresponding directory, or with the directory prefix shown below.

## Start the database and backend

```bash
docker compose up -d database
conda activate account
cd backend
uvicorn main:app --reload
```

The backend runs at `http://127.0.0.1:8000`.

## Start the frontend

Open another terminal at the repository root and run:

```bash
npm --prefix frontend run dev
```

The frontend runs at `http://127.0.0.1:5173`. Running `npm run dev` directly
from the repository root does not work because `package.json` belongs to the
`frontend` directory.

## Run all tests

```bash
conda run -n account pytest -q backend/tests
npm --prefix frontend test
npm --prefix frontend run build
```

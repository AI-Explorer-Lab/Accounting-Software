# Accounting Software Backend

FastAPI architecture scaffold backed by PostgreSQL. It intentionally contains no
accounting business implementation yet.

## Start locally

From the repository root:

```bash
docker compose up -d database
conda env create -f backend/environment.yml
conda activate account
cd backend
uvicorn main:app --reload
```

If the environment already exists, update it with:

```bash
conda env update -n account -f backend/environment.yml --prune
```

The API documentation is available at `http://127.0.0.1:8000/docs`. The health
endpoint is `http://127.0.0.1:8000/api/v1/health`.

## Configuration

Non-sensitive defaults live in `config/app.yaml`. Select an environment with
`ACCOUNT_ENV`, and override nested values with Dynaconf variables such as
`ACCOUNT_DB__PASSWORD`.

## Test

```bash
conda run -n account pytest -q backend/tests
```

## Container build

```bash
docker build -t account-backend backend
```

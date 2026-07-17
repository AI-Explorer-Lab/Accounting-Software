# Accounting Software Backend

FastAPI accounting API backed by PostgreSQL. It currently supports creating
income and expense transactions.

## Start locally

From the repository root:

```bash
docker compose up -d database
conda env create -f backend/environment.yml
conda activate account
cd backend
uvicorn main:app --reload --port 8101
```

If the environment already exists, update it with:

```bash
conda env update -n account -f backend/environment.yml --prune
```

When the backend is run on its own, the API documentation is available at
`http://127.0.0.1:8101/docs` and the health endpoint is
`http://127.0.0.1:8101/api/v1/health`. The repository `start.sh` exposes the
whole application on port `8101` and uses an internal backend port to avoid a
collision with Vite.

## Create a transaction

`POST /api/transactions` accepts both income and expense transactions:

```json
{
  "amount": "125.50",
  "category": "Food",
  "description": "Team lunch",
  "transaction_date": "2026-07-14",
  "transaction_type": "expense"
}
```

`amount` must be greater than zero. `transaction_type` must be `income` or
`expense`. Development startup automatically creates the `transactions` table
when the configured PostgreSQL database is available.

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

# server

V-Market's MiniApp Backend. The docs call this component "MiniApp Backend":

```
MiniApp  ──authCode──>  server/  ──client_secret──>  V-App Open API
(React)                          <──── user_id ────
   <──── JWT ────────────────────
```

The MiniApp cannot call the Open API itself: the token exchange needs
`client_secret`, and the docs state `user_id` is only obtainable from the
backend. The `getUserInfo` JSAPI returns a name and avatar, but deliberately no
identifier.

## Run

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe -m uvicorn app.main:app --port 4000 --reload
```

Swagger: http://127.0.0.1:4000/docs

Needs a V-App to talk to. In development that is [`../mock-openAPI`](../mock-openAPI),
running on port 4001.

## Endpoints

| Method | Path | |
|---|---|---|
| POST | `/auth/session` | `{authCode}` → JWT, or `CONSENT_REQUIRED` |
| GET | `/healthz` | |

## Login flow

```
getAuthCode(['auth'])  ->  POST /auth/session
   known user  -> AUTHENTICATED         (silent, no consent screen)
   new user    -> CONSENT_REQUIRED
                  -> getAuthCode(['profile','phone'])
                  -> POST /auth/session -> AUTHENTICATED
```

Consent appears exactly once per user, ever. Source:
`developer.v-app.vn/backend-api/resources/login-free-system`.

`role` and `sellerId` are V-Market's data, looked up by `user_id`. V-App has no
notion of buyer or seller.

## Tests

```bash
.venv\Scripts\python.exe -m pytest
```

`mock-openAPI` must be running first — the tests skip with instructions if it
is not. They are not wired to boot it in-process on purpose: the gateway should
reach V-App over the network, exactly as it will against the real API.

`tests/test_contract.py` runs against whatever `VAPP_BASE_URL` points at, so the
same suite verifies the real API:

```bash
VAPP_BASE_URL=https://api.v-app.vn VAPP_TEST_AUTH_CODE=<from a device> pytest
```

All green means the swap is done; a red test points at exactly what differs.

## Swapping in the real API

Change three lines in `.env` — `VAPP_BASE_URL`, `VAPP_CLIENT_ID`,
`VAPP_CLIENT_SECRET` — and stop running `mock-openAPI`. There is no mock/real
flag in the code; `app/vapp/gateway.py` is the single implementation and only
ever sees a URL.

## Migrations (Alembic)

The schema lives in the SQLAlchemy models. Dev and tests build it directly
with `create_all` for speed; Alembic is the path for a database that must
evolve without being dropped — a real deployment.

- Baseline: `migrations/versions/` holds the initial schema. A fresh
  database is brought up to date with `python -m alembic upgrade head`.
- A database that already has the tables (e.g. this dev one, built by
  `create_all`) is reconciled once with `python -m alembic stamp head`.
- After changing a model: `python -m alembic revision --autogenerate -m "..."`,
  review the generated file, then `python -m alembic upgrade head`.

The URL comes from app settings; override it for a one-off with
`ALEMBIC_URL=... python -m alembic ...`.

# mock-openAPI

Mock of the V-App Open API, for local development.

It mocks only what V-Market actually calls:

| Method | Path | |
|---|---|---|
| POST | `/oauth2/token/exchange` | authCode → access token |
| POST | `/oauth2/token/refresh` | |
| GET | `/open/identity/v1/userinfo` | returns fields **per scope** |

Plus three endpoints that **do not exist on the real V-App**. They stand in for
the `getAuthCode` JSAPI, which needs an `appIdentifier` registered in DevCenter,
and for signing up with Vingroup:

| Method | Path | |
|---|---|---|
| GET | `/simulator/users` | list accounts |
| POST | `/simulator/users` | register an account (`{name}`) |
| POST | `/simulator/authcode` | issue an authCode |

Registration lives here rather than in `server/` because that is where it lives
in production: a person signs up with Vingroup, and a MiniApp only ever receives
an identity that already exists. V-Market never grows a password of its own.

## Run

Needs the database from `docker-compose.yml` at the repository root:

```bash
docker compose up -d

py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe -m uvicorn main:app --port 4001 --reload
```

Accounts live in the `vapp_mock` database — **separate from V-Market's**, so
V-Market cannot read V-App's tables even by accident. Issued authCodes and
access tokens stay in memory: they live 60s and 1h, and losing them on restart
is correct.

Swagger: http://127.0.0.1:4001/docs

> Port 4001 because `v-miniapp-cli` already takes **3000–3999** (Simulator) and
> **8080–8999** (Mini App server). 4000 is reserved for `server/`.

Then point the backend at it (`server/.env`):

```
VAPP_BASE_URL=http://127.0.0.1:4001
```

To use the real API, change that to `https://api.v-app.vn` and stop running this
folder. The backend has no mock/real flag — it only knows a URL.

## Design rules

Stricter than the real thing, never looser. Where the docs are silent, pick the
stricter reading, so bugs surface now instead of on integration day:

- **Filter by scope** — `auth` returns `user_id` only. Returning every field
  regardless of scope would let the backend get used to always having
  `phone_number`, then break at checkout.
- `auth_code` is **single use**, 60s TTL
- Access tokens are **opaque** — no `user_id` encoded inside
- Envelope `{code, message, data}` — **`code: 0` means success**; HTTP 200 alone
  does not

Error codes `101xx` come from the real docs. `102xx` (authCode failures) are
invented, since the docs don't publish them — so callers must branch on
`code != 0`, never on a specific number.

Source: `developer.v-app.vn/backend-api/open-api/*`,
`/backend-api/resources/user-profile`.

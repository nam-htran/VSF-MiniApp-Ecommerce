# mock-openAPI

Mock of the V-App Open API, for local development.

It mocks only what V-Market actually calls:

| Method | Path | |
|---|---|---|
| POST | `/oauth2/token/exchange` | authCode → access token |
| POST | `/oauth2/token/refresh` | |
| GET | `/open/identity/v1/userinfo` | returns fields **per scope** |

Plus two endpoints that **do not exist on the real V-App**. They stand in for
the `getAuthCode` JSAPI, which needs an `appIdentifier` registered in DevCenter:

| Method | Path | |
|---|---|---|
| GET | `/simulator/users` | 3 seed accounts |
| POST | `/simulator/authcode` | issue an authCode |

## Run

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe -m uvicorn main:app --port 4001 --reload
```

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

# Bank Integration Documentation (KoshConnect Mock API)

Last updated: 2026-04-17

This document is for frontend integration updates after backend changes to support the new KoshConnect mock API contract.

## 1) Base URLs

- Backend API base (this project):
  - /api/v1
- External mock API base (KoshConnect):
  - Uses environment variable KOSHCONNECT_BASE_URL
  - Default: https://koshconnect.onrender.com
  - Optional signing env vars used by backend when mock API enforces signed token requests:
    - KOSHCONNECT_SIGNING_SECRET
    - KOSHCONNECT_SIGN_TOKEN_REQUEST (default: false)

## 2) Authentication

### Frontend -> Backend

Use your app auth token for all protected backend routes below.

Header:
- Authorization: Bearer <your-app-jwt>

### Backend -> KoshConnect (handled by backend)

Backend uses KoshConnect bearer token internally for sync.

Header:
- Authorization: Bearer <koshconnect_access_token>

## 3) Backend Endpoints Frontend Should Use

All routes below are mounted under /api/v1.

---

### 3.1 POST /bank/bank-login

Purpose:
- Login to KoshConnect using bank credentials and sync all linked accounts + transactions (+ stock instruments when available).

Auth:
- Required (app JWT)

Content-Type:
- multipart/form-data

Form fields:
- username (string)  -> KoshConnect phone number/username used for /token
- password (string)

Success response (example):

{
  "status": "success",
  "message": "All accounts, transactions, and stock instruments synced successfully.",
  "synced_accounts": [
    {
      "user_id": "a1b2c3d4-e5f6-7788-9900-aabbccddeeff",
      "bank_name": "Nabil Bank",
      "account_number_masked": "****1234",
      "account_type": "Student Savings (Allowance)",
      "balance": 15000.0,
      "account_id": "b2a1c3d4-e5f6-7788-9900-aabbccddeeff"
    }
  ],
  "synced_stock_instruments": 1,
  "bank_token": "<koshconnect_access_token>",
  "synced_accounts_detail": [
    {
      "external_account_id": "b2a1c3d4-e5f6-7788-9900-aabbccddeeff",
      "local_account_id": "8fd2f2da-cf84-4d09-95ad-4426fcccbecf",
      "new_transactions": 12,
      "status": "synced"
    }
  ]
}

Error cases:
- 409: Cannot link to this KoshConnect account.
- 500: KoshConnect auth/network/sync failures

Frontend notes:
- Treat this as the primary connect + initial sync action.
- Store backend response only for UX/debug; persistent data should be fetched from /bank/accounts etc.

---

### 3.2 POST /bank/sync-now

Purpose:
- Trigger immediate re-sync using an already available KoshConnect token.

Auth:
- Required (app JWT)

Request JSON:

{
  "bank_token": "<koshconnect_access_token>"
}

Response:
- Same shape as /bank/bank-login summary.

Frontend notes:
- Use when user explicitly requests refresh and you already hold token from prior flow.

---

### 3.3 GET /bank/sync-status

Purpose:
- Get latest sync metadata.

Auth:
- Required (app JWT)

Success response:

{
  "user_id": "user-uuid-or-id",
  "last_successful_sync": "2026-04-17T05:10:00Z",
  "last_attempted_sync": "2026-04-17T05:10:00Z",
  "last_transaction_fetched_at": "2026-04-16T10:45:16Z",
  "sync_status": "SUCCESS",
  "failure_reason": null
}

Frontend notes:
- Show last sync state and any failure reason to the user.

---

### 3.4 GET /bank/accounts

Purpose:
- Fetch locally stored linked bank accounts.

Auth:
- Required (app JWT)

Success response (array):

[
  {
    "id": "8fd2f2da-cf84-4d09-95ad-4426fcccbecf",
    "user_id": "local-user-id",
    "external_account_id": "b2a1c3d4-e5f6-7788-9900-aabbccddeeff",
    "bank_name": "Nabil Bank",
    "account_number_masked": "****1234",
    "account_type": "Student Savings (Allowance)",
    "balance": 15000.00
  }
]

---

### 3.5 POST /bank/transactions

Purpose:
- Create manual transaction in local backend.

Auth:
- Required (app JWT)

Request JSON:

{
  "source": "MANUAL",
  "date": "2026-04-17T08:30:00Z",
  "amount": 500,
  "currency": "NPR",
  "type": "DEBIT",
  "status": "BOOKED",
  "description": "Lunch",
  "merchant": "Cafe",
  "category": "Food",
  "account_id": "8fd2f2da-cf84-4d09-95ad-4426fcccbecf",
  "external_transaction_id": null
}

Response:
- Created transaction object (includes id and user_id).

Validation notes:
- User must own account_id.
- Manual transaction amount cap logic is enforced by backend.

---

### 3.6 POST /bank/unlink

Purpose:
- Deactivate all linked accounts for current user.

Auth:
- Required (app JWT)

Response:

{
  "message": "All bank accounts have been unlinked successfully."
}

---

### 3.7 DELETE /bank/delete-data

Purpose:
- Delete all transactions for current user.

Auth:
- Required (app JWT)

Response:

{
  "message": "All transaction data has been deleted successfully."
}

---

### 3.8 Legacy/Specific routes (optional UI usage)

- GET /bank/accounts/nabil
- GET /bank/accounts/nabil/transactions

These are bank-specific helper routes and not required for generalized multi-bank UI.

## 4) External KoshConnect Endpoints Used by Backend

These are not called directly by frontend (unless you intentionally bypass backend).

### Primary flow

- POST /token
  - Form data: username, password
  - Backend now sends signed headers when enabled in env:
    - X-Request-ID
    - X-Bank-Signature
  - Returns access_token and accounts array.

- GET /users/me or /users/me/
  - Returns authenticated user profile with user_id.

- GET /users/{user_id}/accounts
  - Returns accounts for that user.

- GET /accounts/{account_id}/transactions
  - Returns transactions for account.

### Stock sync flow

Backend now prefers:
- GET /users/{user_id}/stocks

Fallbacks still supported for compatibility:
- GET /stock-instruments
- GET /instruments
- GET /investments

## 5) Contract Compatibility Improvements Added in Backend

Backend now tolerates these KoshConnect response variations:

- Trailing slash vs no trailing slash in endpoint paths.
- Wrapped list payloads or direct arrays:
  - accounts, data, items
  - transactions, data, items
- Field aliases:
  - account_id or id
  - transaction_id or id
- Missing optional fields (defaults applied safely for currency/type/status/date where needed).

Additional integration hardening:
- /token request body is sent as deterministic URL-encoded raw payload and signed as request_id.raw_body when signing is enabled.
- /token calls follow redirects (avoids 307 failures due to slash redirect behavior).

## 9) Troubleshooting (401 / 307 on /bank/bank-login)

If you see:
- HTTP error during KoshConnect login: 401 - {"detail":"Could not validate credentials"}
- HTTP error during KoshConnect login: 307

Check backend .env first:

When token signing is required by mock API:
- KOSHCONNECT_SIGN_TOKEN_REQUEST=true
- KOSHCONNECT_SIGNING_SECRET=<exact third-party signing secret>

When token signing is NOT required by mock API:
- KOSHCONNECT_SIGN_TOKEN_REQUEST=false

Also verify:
- KOSHCONNECT_BASE_URL is correct for current mock deployment.
- username/password values are exactly what the third-party /token expects.

## 6) Data Mapping Reference

### Account mapping

External -> Local
- account_id -> external_account_id
- bank_name -> bank_name
- account_number_masked -> account_number_masked
- account_type -> account_type
- balance -> balance

### Transaction mapping

External -> Local
- transaction_id -> external_transaction_id
- account_id -> local account relation (resolved via external account)
- date -> date
- amount -> amount
- currency -> currency
- type -> type
- status -> status
- description -> description
- merchant -> merchant
- category -> category

## 7) Frontend Migration Checklist

1. Keep calling backend routes under /api/v1/bank; do not call KoshConnect directly unless planned.
2. Use multipart/form-data for /bank/bank-login.
3. Use /bank/sync-status to drive sync-state UI and retry messaging.
4. Refresh local account lists from /bank/accounts after sync success.
5. Handle 409 from bank-login/sync-now as account-link conflict.
6. Keep manual transaction flow unchanged except validating account ownership and error messages.

## 8) Example Frontend Call Snippets

### Connect and sync

POST /api/v1/bank/bank-login
Headers:
- Authorization: Bearer <app-jwt>
Body (form-data):
- username: 9862606079
- password: Pass@1234

### Check sync status

GET /api/v1/bank/sync-status
Headers:
- Authorization: Bearer <app-jwt>

### Sync now (token-based)

POST /api/v1/bank/sync-now
Headers:
- Authorization: Bearer <app-jwt>
Content-Type: application/json
Body:
{
  "bank_token": "<koshconnect_access_token>"
}

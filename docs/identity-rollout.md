# Identity / web auth — staging & prod checklist

See also [adr-identity-web-auth.md](adr-identity-web-auth.md) and PRODUCT.md «Identity & Web Auth».

## Before enabling merge execute

1. `EMAIL_MERGE_CONFIRMATION_ENABLED=true` on staging.
2. Run: `pytest tests/test_account_merge_service.py tests/test_email_claim_pipeline_services.py tests/test_auth_token_service.py tests/test_auth_api.py -q`
3. Manual: two accounts, same email → dual confirm → data on survivor.
4. Web-only target (no TG/MAX): OTP email arrives; `POST /api/v1/confirm-email-merge-otp/`.
5. Then set `EMAIL_MERGE_EXECUTE_ENABLED=true` on staging; re-verify merge.
6. Prod: SMTP configured (`EMAIL_HOST`…), `WEB_APP_URL` points at public web, `EMAIL_FAIL_SILENTLY=false` recommended.
7. Keep `EMAIL_MERGE_WEB_CONFIRM_FALLBACK_ENABLED=false` unless ops need web token fallback.

## Bot → web

- Recover access (no SMTP): `POST /api/v1/web-access/claim/` with `{email, platform?}` → bot confirm → link `{WEB_APP_URL}/auth/set-password/<token>/` → `POST /api/v1/web-access/set-password/`
- SPA routes: `/recover`, `/auth/set-password/:token`
- Telegram `/web` → `{WEB_APP_URL}/auth/telegram/?token=` (JWT handoff; UI later)
- MAX `/web` → `{WEB_APP_URL}/auth/max/?token=` (JWT handoff; UI later)

`WEB_APP_URL` must point at the consumer SPA (local Vite: `http://localhost:3000`) so bot links open the set-password page.

## Web → bot

- API `generate-link` / `generate-max-link` (cabinet UI returns with the next web UI).

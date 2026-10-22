# ADR: Web identity (web-first + bot-first)

## Status

Accepted (implementation tranche B).

## Context

Users already exist via Telegram and MAX, often without a usable web password. Identity layer adds email+password and (when consumer web UI exists) Django sessions. Email is already the unique identity key (`email_hash`) and the merge bridge. Previous Window-night web UI was removed pending a new design direction.

## Decision

1. One `User` per person; messengers and email/password are channels.
2. Web-first: register/login without requiring TG/MAX.
3. Bot-first web access: messenger auth token → Django session; password claim confirmed **in the bot**.
4. Email merge: dual transport confirm; email OTP only when target has no TG/MAX; execute behind `EMAIL_MERGE_EXECUTE_ENABLED`.
5. Transactional email via Django SMTP (`EmailDeliveryService`) for password reset and web-only merge OTP.

## Consequences

- Additive models/tokens only; no destructive identity migrations.
- When consumer web UI returns, `/web` URLs must hit session handoff (`/auth/telegram/`, `/auth/max/`), not only JWT SPA paths. Until then, JWT API handoff is the supported path.
- Ops must configure SMTP and enable merge execute only after staging verification.

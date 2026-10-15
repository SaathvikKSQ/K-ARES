# K-AERS — Security & Privacy Requirements

**Version:** 1.0.0 · **Status:** Draft for review

## 1. Authentication & Authorization (MVP)

- SR-1: All `/api/v1` endpoints (except `GET /health`, `POST /auth/login`) require an authenticated session (signed cookie) or bearer token.
- SR-2: Users stored with bcrypt (cost ≥ 12) password hashes; no plaintext anywhere.
- SR-3: Roles `admin | editor | viewer`: viewer = read-only; editor = manage apps/datasets/runs; admin = user management + settings. Enforcement in service layer, not just routes.
- SR-4: Login rate limiting (e.g., 5 attempts/15 min/IP) and constant-time failure responses.
- SR-5: Session/token expiry configurable; logout invalidates server-side session.
- SR-6 (F): SSO/enterprise IdP integration — design hooks only.

## 2. Secrets & Credential Handling

- SR-7: No secrets in code, specs, tests, logs, or responses. All credentials from environment or K-AERS-encrypted storage.
- SR-8: Application connection credentials are encrypted at rest using Fernet (AES-128-CBC + HMAC) with `SECRET_ENCRYPTION_KEY` from the environment (32-byte urlsafe base64). Key rotation documented.
- SR-9: API responses expose only `has_credentials` + `credentials_updated_at`; credential fields are write-only.
- SR-10: Log redaction filter removes values of keys matching `api_key|token|password|secret|authorization` (case-insensitive) before serialization.
- SR-11: Exports and reports never include credentials or connection secrets.

## 3. Input & Upload Validation

- SR-12: Dataset uploads restricted to `.jsonl`/`.csv`, ≤ 10 MB, ≤ 20,000 rows; content sniffing (not just extension); parsing bounded (row/size caps) to prevent decompression bombs and memory exhaustion.
- SR-13: All API payloads validated by Pydantic with strict types; unknown-field policy documented per schema.
- SR-14: File paths for storage are server-generated (UUID keys); user input never reaches filesystem paths.

## 4. SSRF & Outbound Request Safety

- SR-15: User-supplied URLs validated: scheme must be http/https; resolve host and block private/loopback/link-local ranges (127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7, fe80::/10) unless `ALLOW_PRIVATE_TARGETS=true` (dev only).
- SR-16: All outbound adapter calls: connect+read timeouts, max response size (e.g., 5 MB), max redirects (0–2, revalidated), per-run concurrency cap, optional rate limit.
- SR-17: Connection test endpoint performs only a lightweight, safe request (e.g., GET health) — never user-controlled arbitrary paths.

## 5. Data Handling & Privacy

- SR-18: Evaluation data (prompts, outputs, retrieved passages, traces) may be sensitive; access control scoped per deployment (single-tenant MVP; project scoping hooks for later).
- SR-19: Document in UI + docs what data is sent where: target application receives test inputs; configured LLM judge provider receives inputs/outputs/references for judged metrics.
- SR-20: Retention configurable (`RETENTION_DAYS` for artifacts/exports; runs explicit). Deletion cascades documented.
- SR-21: Use synthetic data in sample datasets and tests; no real PII.
- SR-22: Sanitize displayed outputs and error messages (frontend renders as text, never HTML; backend strips/truncates oversized error payloads).

## 6. Security Evaluation Suite Constraints

- SR-23: Payloads are static, versioned, harmless, and reviewed in code review; no destructive operations, no real exploit tooling, no attacks on third-party systems.
- SR-24: The suite tests the registered application only, in environments the owner designates.
- SR-25: UI/reports state: passing the suite does not prove security; list covered vs uncovered risk categories explicitly.

## 7. Platform Hardening

- SR-26: CORS restricted to configured frontend origins; security headers (HSTS behind TLS, X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy).
- SR-27: Global request size limits; per-IP request throttling on write endpoints (configurable).
- SR-28: Docker images run as non-root; no secrets baked into images; dependencies pinned with lockfiles.
- SR-29: Structured logs exclude request bodies by default (opt-in debug redacted mode).
- SR-30: Known-limitations section maintained in README (honesty over marketing — no untested "enterprise-grade" claims).

## Threat Model Snapshot (STRIDE-lite)

| Threat | Mitigation refs |
|---|---|
| Credential theft from DB/logs/UI | SR-7–SR-11 |
| SSRF via app registration | SR-15–SR-17 |
| Malicious dataset upload (DoS/injection) | SR-12–SR-14 |
| Unauthorized data access | SR-1–SR-3, SR-18 |
| Abuse of security suite against third parties | SR-23–SR-24 |
| Log/trace data leakage | SR-10, SR-19, SR-29 |

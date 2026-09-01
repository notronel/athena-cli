# AthenaNet CLI

A read-only Python command-line client for athenahealth FHIR R4 SMART v2. It can validate credentials, search patients, and retrieve document metadata. It deliberately has no command that creates, updates, uploads, reschedules, cancels, or deletes athenahealth data.

## Setup

Create an athenahealth sandbox application with only the required read permissions. Export credentials in your shell; this tool does not read or save a `.env` file, access token, response body, or patient cache.

```sh
export ATHENA_CLIENT_ID="your-client-id"
export ATHENA_CLIENT_SECRET="your-client-secret"
export ATHENA_SCOPE="system/Patient.rs system/DocumentReference.rs"

python -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

`ATHENA_FHIR_BASE_URL` defaults to the athenaPractice v25 sandbox. Set it or `ATHENA_TOKEN_URL` only if athenahealth supplies different values.

## Commands

```sh
athena auth check
athena patients search --first-name Ada --last-name Lovelace --dob 1815-12-10
athena documents list --patient-id 123 --from-date 2026-01-01 --to-date 2026-09-01
athena documents get --patient-id 123 --document-id 456
```

Commands print a minimum-field terminal table by default. Add `--json` to receive the normalized API response for scripting. Any field names or endpoint capabilities that differ by athenahealth product are surfaced as clear API errors; the registered Developer Portal documentation is authoritative.

List commands request up to 50 records by default and paginate automatically. Use `--limit 1..500` to set a smaller or larger bounded result set. Appointment access is unavailable because the enabled application does not expose a general Appointment read/search scope.

## Safety and privacy

- Only OAuth token acquisition uses `POST`; every business-data request is `GET`.
- The client does not expose write operations or a generic request command.
- Credentials are read from environment variables and never printed.
- The CLI does not persist PHI, tokens, or API responses and does not enable HTTP request/response logging.

## Development

```sh
.venv/bin/pytest
```

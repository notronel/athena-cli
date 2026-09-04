# AthenaNet CLI

A read-only Python command-line client for athenahealth FHIR R4 SMART v2. It can validate credentials, search patients, and retrieve document metadata. It deliberately has no command that creates, updates, uploads, reschedules, cancels, or deletes athenahealth data.

## Setup

Create an athenahealth sandbox application with only the required read permissions. The simplest setup is interactive and saves credentials only to the local `.env` file with owner-only permissions.

```sh
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/athena auth setup
```

The setup wizard needs the Client ID and Client Secret for the registered application. Then run `.venv/bin/athena auth check`. The CLI reads `.env` automatically and never prints a secret, writes API responses to disk, or persists tokens. `ATHENA_FHIR_BASE_URL` defaults to athenahealth's FHIR R4 Preview base URL. The CLI reads the public SMART configuration to find the matching token endpoint; override the base URL only if athenahealth supplies a different one.

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

from __future__ import annotations

from collections.abc import Mapping
from time import sleep
from typing import Any

import httpx

from .config import AthenaSettings


class AthenaError(RuntimeError):
    """A safe, operator-facing athenahealth API failure."""


class AthenaClient:
    """Read-only FHIR R4 SMART v2 client; only token acquisition uses POST."""

    def __init__(self, settings: AthenaSettings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._http = httpx.Client(timeout=settings.timeout_seconds, transport=transport)
        self._access_token: str | None = None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AthenaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def authenticate(self) -> None:
        try:
            token_url = self.settings.token_url or self._discover_token_url()
            response = self._request(
                "POST", token_url,
                data={"grant_type": "client_credentials", "scope": self.settings.scope},
                auth=(self.settings.client_id, self.settings.client_secret.get_secret_value()),
            )
            token = response.json().get("access_token")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise AthenaError(self._safe_error("authentication", exc)) from exc
        if not isinstance(token, str) or not token:
            raise AthenaError("Authentication succeeded but did not return an access token.")
        self._access_token = token

    def _discover_token_url(self) -> str:
        try:
            response = self._request(
                "GET",
                self.settings.smart_configuration_url,
                headers={"Accept": "application/json"},
            )
            token_url = response.json().get("token_endpoint")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise AthenaError(self._safe_error("SMART configuration", exc)) from exc
        if not isinstance(token_url, str) or not token_url.startswith("https://"):
            raise AthenaError("Athenahealth SMART configuration did not provide a valid token endpoint.")
        return token_url

    def search_patients(self, *, patient_id: str | None = None, first_name: str | None = None, last_name: str | None = None, dob: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if not any((patient_id, first_name, last_name, dob)):
            raise AthenaError("Provide at least one patient search field.")
        if patient_id:
            return [self._resource(f"Patient/{patient_id}")]
        return self._search("Patient", {"given": first_name, "family": last_name, "birthdate": dob}, limit)

    def list_documents(self, *, patient_id: str, from_date: str | None = None, to_date: str | None = None, document_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: list[tuple[str, str]] = [("patient", patient_id)]
        if from_date:
            params.append(("date", f"ge{from_date}"))
        if to_date:
            params.append(("date", f"le{to_date}"))
        if document_type:
            params.append(("type", document_type))
        return self._search("DocumentReference", params, limit)

    def get_document(self, *, patient_id: str, document_id: str) -> dict[str, Any]:
        document = self._resource(f"DocumentReference/{document_id}")
        subject = document.get("subject", {})
        if isinstance(subject, Mapping) and subject.get("reference") not in {f"Patient/{patient_id}", patient_id}:
            raise AthenaError("Document does not belong to the requested patient.")
        return document

    def _search(self, resource_type: str, params: Mapping[str, str | None] | list[tuple[str, str]], limit: int) -> list[dict[str, Any]]:
        query = [(key, value) for key, value in (params.items() if isinstance(params, Mapping) else params) if value is not None]
        query.append(("_count", str(min(50, limit))))
        resources: list[dict[str, Any]] = []
        next_url: str | None = f"{self.settings.fhir_base_url}/{resource_type}"
        while next_url and len(resources) < limit:
            payload = self._get_url(next_url, query)
            query = []
            if not isinstance(payload, Mapping) or payload.get("resourceType") != "Bundle":
                raise AthenaError(f"Unexpected {resource_type} search response format.")
            for entry in payload.get("entry", []):
                if isinstance(entry, Mapping) and isinstance(entry.get("resource"), Mapping):
                    resources.append(dict(entry["resource"]))
                    if len(resources) == limit:
                        return resources
            next_url = self._bundle_next(payload)
        return resources

    def _resource(self, path: str) -> dict[str, Any]:
        payload = self._get_url(f"{self.settings.fhir_base_url}/{path}")
        if not isinstance(payload, Mapping):
            raise AthenaError("Unexpected FHIR resource response format.")
        return dict(payload)

    def _get_url(self, url: str, params: list[tuple[str, str]] | None = None) -> Any:
        if self._access_token is None:
            self.authenticate()
        try:
            response = self._request("GET", url, params=params, headers={"Authorization": f"Bearer {self._access_token}", "Accept": "application/fhir+json"})
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AthenaError(self._safe_error("read request", exc)) from exc

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: httpx.HTTPError | None = None
        for attempt in range(3):
            try:
                response = self._http.request(method, url, **kwargs)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    return response
                last_error = httpx.HTTPStatusError("transient response", request=response.request, response=response)
            except httpx.RequestError as exc:
                last_error = exc
            if attempt < 2:
                sleep(0.2 * (2**attempt))
        if last_error is not None:
            raise last_error
        raise AthenaError("Request could not be completed.")

    @staticmethod
    def _bundle_next(bundle: Mapping[str, Any]) -> str | None:
        for link in bundle.get("link", []):
            if isinstance(link, Mapping) and link.get("relation") == "next" and isinstance(link.get("url"), str):
                return link["url"]
        return None

    @staticmethod
    def _safe_error(operation: str, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Athenahealth {operation} failed with HTTP {exc.response.status_code}. Check API permissions and request fields."
        if isinstance(exc, httpx.TimeoutException):
            return f"Athenahealth {operation} timed out."
        if isinstance(exc, httpx.RequestError):
            return f"Athenahealth {operation} could not reach the configured API endpoint."
        return f"Athenahealth {operation} returned an invalid response."

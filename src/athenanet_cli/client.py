from __future__ import annotations

from collections.abc import Mapping
from time import sleep
from typing import Any

import httpx

from .config import AthenaSettings


class AthenaError(RuntimeError):
    """A safe, operator-facing athenahealth API failure."""


class AthenaClient:
    """Small read-only client. OAuth token POST is the sole non-GET request."""

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

    @property
    def api_base(self) -> str:
        return f"{self.settings.base_url}/{self.settings.practice_id}"

    @property
    def token_url(self) -> str:
        return f"{self.api_base}/{self.settings.token_path}"

    def authenticate(self) -> None:
        payload: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret.get_secret_value(),
        }
        if self.settings.scope:
            payload["scope"] = self.settings.scope
        try:
            response = self._request("POST", self.token_url, data=payload)
            token = response.json().get("access_token")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise AthenaError(self._safe_error("authentication", exc)) from exc
        if not isinstance(token, str) or not token:
            raise AthenaError("Authentication succeeded but did not return an access token.")
        self._access_token = token

    def search_patients(
        self,
        *,
        patient_id: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        dob: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not any((patient_id, first_name, last_name, dob)):
            raise AthenaError("Provide at least one patient search field.")
        return self._get_collection(
            "patients",
            {"patientid": patient_id, "firstname": first_name, "lastname": last_name, "dob": dob, "limit": str(limit)},
            "patients",
        )

    def list_appointments(
        self,
        *,
        patient_id: str,
        from_date: str,
        to_date: str,
        department_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._get_collection(
            "appointments",
            {
                "patientid": patient_id,
                "startdate": from_date,
                "enddate": to_date,
                "departmentid": department_id,
                "status": status,
                "limit": str(limit),
            },
            "appointments",
        )

    def list_documents(
        self, *, patient_id: str, from_date: str | None = None, to_date: str | None = None, document_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return self._get_collection(
            f"patients/{patient_id}/documents",
            {"fromdate": from_date, "todate": to_date, "documenttype": document_type, "limit": str(limit)},
            "documents",
        )

    def get_document(self, *, patient_id: str, document_id: str) -> dict[str, Any]:
        payload = self._get(f"patients/{patient_id}/documents/{document_id}")
        if isinstance(payload, list):
            if not payload:
                raise AthenaError("Document was not found.")
            return self._as_mapping(payload[0])
        if isinstance(payload, Mapping) and isinstance(payload.get("document"), Mapping):
            return dict(payload["document"])
        return self._as_mapping(payload)

    def _get_collection(self, path: str, params: dict[str, str | None], key: str) -> list[dict[str, Any]]:
        limit = int(params.pop("limit", "50") or "50")
        offset = 0
        items: list[dict[str, Any]] = []
        while len(items) < limit:
            page_size = min(50, limit - len(items))
            payload = self._get(path, {**params, "limit": str(page_size), "offset": str(offset)})
            page = self._collection_from_payload(payload, key)
            items.extend(page)
            if len(page) < page_size:
                break
            offset += len(page)
        return items[:limit]

    def _collection_from_payload(self, payload: Any, key: str) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [self._as_mapping(item) for item in payload]
        if isinstance(payload, Mapping):
            collection = payload.get(key, payload.get("data", []))
            if isinstance(collection, list):
                return [self._as_mapping(item) for item in collection]
        raise AthenaError(f"Unexpected {key} response format.")

    def _get(self, path: str, params: dict[str, str | None] | None = None) -> Any:
        if self._access_token is None:
            self.authenticate()
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        try:
            response = self._request(
                "GET",
                f"{self.api_base}/{path.lstrip('/')}",
                params=clean_params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AthenaError(self._safe_error("read request", exc)) from exc

    @staticmethod
    def _as_mapping(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise AthenaError("Unexpected item in API response.")
        return dict(value)

    @staticmethod
    def _safe_error(operation: str, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Athenahealth {operation} failed with HTTP {exc.response.status_code}. Check API permissions and request fields."
        if isinstance(exc, httpx.TimeoutException):
            return f"Athenahealth {operation} timed out."
        if isinstance(exc, httpx.RequestError):
            return f"Athenahealth {operation} could not reach the configured API endpoint."
        return f"Athenahealth {operation} returned an invalid response."

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Retry transient failures only; request and response payloads are never logged."""
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

import httpx
import pytest
from pydantic import SecretStr

from athenanet_cli.client import AthenaClient, AthenaError
from athenanet_cli.config import AthenaSettings


def settings() -> AthenaSettings:
    return AthenaSettings(client_id="client", client_secret=SecretStr("secret"), fhir_base_url="https://example.test/demo")


def test_patient_search_uses_fhir_bundle_and_read_only_get() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, json={"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient", "id": "1"}}]})

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        assert client.search_patients(first_name="Ada") == [{"resourceType": "Patient", "id": "1"}]

    assert [request.method for request in requests] == ["POST", "GET"]
    assert requests[0].headers["authorization"].startswith("Basic ")
    assert requests[0].content == b"grant_type=client_credentials&scope=system%2FPatient.rs+system%2FDocumentReference.rs"
    assert requests[1].url.path == "/demo/fhir/Patient"
    assert requests[1].url.params["given"] == "Ada"


def test_document_search_uses_patient_filter_and_fhir_date_prefixes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token"})
        assert request.url.params.get_list("date") == ["ge2026-01-01", "le2026-02-01"]
        assert request.url.params["patient"] == "p1"
        return httpx.Response(200, json={"resourceType": "Bundle", "entry": []})

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        assert client.list_documents(patient_id="p1", from_date="2026-01-01", to_date="2026-02-01") == []


def test_missing_patient_search_field_is_rejected_before_network() -> None:
    with AthenaClient(settings(), httpx.MockTransport(lambda _: pytest.fail("network should not be called"))) as client:
        with pytest.raises(AthenaError, match="at least one"):
            client.search_patients()


def test_http_error_does_not_expose_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(403, content=b"sensitive error details", request=request)

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        with pytest.raises(AthenaError) as error:
            client.list_documents(patient_id="1")
    assert "sensitive" not in str(error.value)

import json

import httpx
import pytest
from pydantic import SecretStr

from athenanet_cli.client import AthenaClient, AthenaError
from athenanet_cli.config import AthenaSettings


def settings() -> AthenaSettings:
    return AthenaSettings(practice_id="42", client_id="client", client_secret=SecretStr("secret"), base_url="https://example.test/v1")


def test_search_authenticates_then_uses_get_only_for_patient_data() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, json={"patients": [{"patientid": "1"}]})

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        assert client.search_patients(first_name="Ada") == [{"patientid": "1"}]

    assert [request.method for request in requests] == ["POST", "GET"]
    assert requests[1].url.path == "/v1/42/patients"
    assert requests[1].url.params["firstname"] == "Ada"


def test_missing_patient_search_field_is_rejected_before_network() -> None:
    with AthenaClient(settings(), httpx.MockTransport(lambda _: pytest.fail("network should not be called"))) as client:
        with pytest.raises(AthenaError, match="at least one"):
            client.search_patients()


def test_http_error_does_not_expose_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(403, content=b"sensitive error details")

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        with pytest.raises(AthenaError) as error:
            client.list_documents(patient_id="1")
    assert "sensitive" not in str(error.value)


def test_document_detail_accepts_single_item_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, content=json.dumps([{"documentid": "9"}]))

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        assert client.get_document(patient_id="1", document_id="9") == {"documentid": "9"}


def test_collection_paginates_to_the_requested_limit() -> None:
    offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        offsets.append(request.url.params["offset"])
        start = int(request.url.params["offset"])
        page_size = int(request.url.params["limit"])
        return httpx.Response(200, json={"patients": [{"patientid": str(number)} for number in range(start, start + page_size)]})

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        patients = client.search_patients(first_name="Ada", limit=75)

    assert len(patients) == 75
    assert offsets == ["0", "50"]


def test_retries_a_transient_server_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"access_token": "token"})

    with AthenaClient(settings(), httpx.MockTransport(handler)) as client:
        client.authenticate()
    assert attempts == 2

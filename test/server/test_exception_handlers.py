import pytest

from hubvault.errors import ConflictError, HubVaultError
from hubvault.server.exception_handlers import register_exception_handlers
from test.support import get_fastapi_test_client


@pytest.mark.unittest
class TestServerExceptionHandlers:
    def test_exception_handlers_map_conflict_generic_and_http_errors(self):
        fastapi = pytest.importorskip("fastapi")
        TestClient = get_fastapi_test_client()
        app = fastapi.FastAPI()
        register_exception_handlers(app)

        @app.get("/conflict")
        async def _conflict():
            raise ConflictError("branch conflict")

        @app.get("/generic")
        async def _generic():
            raise HubVaultError("internal boom")

        @app.get("/http-detail-object")
        async def _http_detail_object():
            raise fastapi.HTTPException(status_code=418, detail={"kind": "teapot"})

        client = TestClient(app)

        conflict_response = client.get("/conflict")
        generic_response = client.get("/generic")
        http_response = client.get("/http-detail-object")

        assert conflict_response.status_code == 409
        assert conflict_response.json()["error"] == {
            "type": "ConflictError",
            "message": "branch conflict",
        }

        assert generic_response.status_code == 500
        assert generic_response.json()["error"] == {
            "type": "HubVaultError",
            "message": "internal boom",
        }

        assert http_response.status_code == 418
        assert http_response.json()["error"] == {
            "type": "HTTPException",
            "message": "{'kind': 'teapot'}",
        }


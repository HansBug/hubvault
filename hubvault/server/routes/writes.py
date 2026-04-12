"""
Write-route factory for :mod:`hubvault.server`.

This module exposes the authenticated mutation endpoints used by the remote
client and frontend write flows. Upload-like operations use a two-step
``commit-plan`` / ``commit`` protocol so callers can avoid stale preflight
results and reduce transferred bytes through exact-copy and chunk-reuse fast
paths.

The module contains:

* :func:`create_writes_router` - Build the ``/api/v1/write`` router
"""

import json

from ..auth import build_write_auth_dependency
from ..deps import build_repo_api_getter
from ..schemas import normalize_commit_manifest_request
from ..serde import encode_commit_info, encode_merge_result
from ..uploads import apply_commit_manifest, plan_commit_manifest
from ...errors import HubVaultValidationError


def _normalize_json_object(payload, endpoint_name: str) -> dict:
    """
    Normalize one route payload that must be a JSON object.

    :param payload: Raw route payload
    :type payload: object
    :param endpoint_name: Endpoint label used in validation messages
    :type endpoint_name: str
    :return: Normalized JSON object payload
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload is not an object.
    """

    if not isinstance(payload, dict):
        raise HubVaultValidationError("%s request body must be a JSON object." % (endpoint_name,))
    return payload


def _require_string_field(payload: dict, field_name: str, endpoint_name: str) -> str:
    """
    Require one string field from a route payload.

    :param payload: Normalized JSON object payload
    :type payload: dict
    :param field_name: Required field name
    :type field_name: str
    :param endpoint_name: Endpoint label used in validation messages
    :type endpoint_name: str
    :return: Normalized string field
    :rtype: str
    :raises HubVaultValidationError: Raised when the field is missing or not a
        string.
    """

    value = payload.get(field_name)
    if not isinstance(value, str):
        raise HubVaultValidationError("%s.%s must be a string." % (endpoint_name, field_name))
    return value


def _optional_string_field(payload: dict, field_name: str, endpoint_name: str):
    """
    Normalize one optional string field from a route payload.

    :param payload: Normalized JSON object payload
    :type payload: dict
    :param field_name: Optional field name
    :type field_name: str
    :param endpoint_name: Endpoint label used in validation messages
    :type endpoint_name: str
    :return: Normalized string value or ``None``
    :rtype: Optional[str]
    :raises HubVaultValidationError: Raised when the field is not a string.
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HubVaultValidationError("%s.%s must be a string." % (endpoint_name, field_name))
    return value


def _optional_bool_field(payload: dict, field_name: str, endpoint_name: str, default: bool = False) -> bool:
    """
    Normalize one optional boolean field from a route payload.

    :param payload: Normalized JSON object payload
    :type payload: dict
    :param field_name: Optional field name
    :type field_name: str
    :param endpoint_name: Endpoint label used in validation messages
    :type endpoint_name: str
    :param default: Default value when the field is missing
    :type default: bool
    :return: Normalized boolean field
    :rtype: bool
    :raises HubVaultValidationError: Raised when the field is not boolean.
    """

    value = payload.get(field_name)
    if value is None:
        return bool(default)
    if not isinstance(value, bool):
        raise HubVaultValidationError("%s.%s must be a boolean." % (endpoint_name, field_name))
    return value


async def _parse_commit_apply_payload(request) -> tuple:
    """
    Parse a write-commit apply payload from JSON or multipart form data.

    :param request: Incoming FastAPI request
    :type request: fastapi.Request
    :return: Tuple of ``(payload, uploads)``
    :rtype: tuple
    :raises HubVaultValidationError: Raised when the payload is malformed.
    """

    content_type = str(request.headers.get("content-type", ""))
    if content_type.startswith("multipart/form-data"):
        try:
            form = await request.form()
        except ValueError as err:
            raise HubVaultValidationError("Invalid multipart payload: %s." % (err,))
        manifest_text = form.get("manifest")
        if not isinstance(manifest_text, str):
            raise HubVaultValidationError("multipart form field 'manifest' must contain JSON text.")
        try:
            payload = json.loads(manifest_text)
        except ValueError as err:
            raise HubVaultValidationError("multipart form field 'manifest' must contain valid JSON: %s." % (err,))
        uploads = {}
        for field_name, value in form.items():
            if field_name == "manifest":
                continue
            read = getattr(value, "read", None)
            if read is None:
                continue
            uploads[field_name] = bytes(await read())
        return payload, uploads

    try:
        return await request.json(), {}
    except ValueError as err:
        raise HubVaultValidationError("Request body must contain valid JSON: %s." % (err,))


def create_writes_router(*, api=None, api_factory=None, authorizer):
    """
    Build the write router for the server app.

    :param api: Optional repository API reused by the router
    :type api: Optional[hubvault.api.HubVaultApi]
    :param api_factory: Optional zero-argument factory returning one fresh
        repository API per request
    :type api_factory: Optional[Callable[[], hubvault.api.HubVaultApi]]
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing authenticated write endpoints
    :rtype: fastapi.APIRouter
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    :raises TypeError: Raised when both ``api`` and ``api_factory`` are
        provided or when neither input is provided.
    """

    from ...optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="server write routes",
        missing_names={"starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Body = fastapi.Body
    Depends = fastapi.Depends
    Request = fastapi.Request

    router = APIRouter(prefix="/api/v1/write", tags=["write"])
    get_api = build_repo_api_getter(api=api, api_factory=api_factory)
    require_write = build_write_auth_dependency(authorizer)

    @router.post("/commit-plan")
    def commit_plan(payload=Body(...), auth=Depends(require_write)):
        """
        Plan one write-commit upload session.

        :param payload: Raw write-manifest payload
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible upload plan
        :rtype: dict
        """

        del auth
        return plan_commit_manifest(get_api(), normalize_commit_manifest_request(payload))

    @router.post("/commit")
    async def create_commit(request: Request, auth=Depends(require_write)):
        """
        Apply one previously planned write-commit upload session.

        :param request: Incoming HTTP request
        :type request: fastapi.Request
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible commit metadata
        :rtype: dict
        """

        del auth
        payload, uploads = await _parse_commit_apply_payload(request)
        commit_info = apply_commit_manifest(get_api(), normalize_commit_manifest_request(payload), uploads)
        return encode_commit_info(commit_info)

    @router.post("/branches")
    def create_branch(payload=Body(...), auth=Depends(require_write)):
        """
        Create one branch ref.

        :param payload: Raw branch-create payload
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible success marker
        :rtype: dict
        """

        del auth
        data = _normalize_json_object(payload, "create_branch")
        get_api().create_branch(
            branch=_require_string_field(data, "branch", "create_branch"),
            revision=_optional_string_field(data, "revision", "create_branch"),
            exist_ok=_optional_bool_field(data, "exist_ok", "create_branch", default=False),
        )
        return {"ok": True}

    @router.delete("/branches/{branch:path}")
    def delete_branch(branch: str, auth=Depends(require_write)):
        """
        Delete one branch ref.

        :param branch: Branch name to delete
        :type branch: str
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible success marker
        :rtype: dict
        """

        del auth
        get_api().delete_branch(branch=branch)
        return {"ok": True}

    @router.post("/tags")
    def create_tag(payload=Body(...), auth=Depends(require_write)):
        """
        Create one lightweight tag.

        :param payload: Raw tag-create payload
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible success marker
        :rtype: dict
        """

        del auth
        data = _normalize_json_object(payload, "create_tag")
        get_api().create_tag(
            tag=_require_string_field(data, "tag", "create_tag"),
            tag_message=_optional_string_field(data, "tag_message", "create_tag"),
            revision=_optional_string_field(data, "revision", "create_tag"),
            exist_ok=_optional_bool_field(data, "exist_ok", "create_tag", default=False),
        )
        return {"ok": True}

    @router.delete("/tags/{tag:path}")
    def delete_tag(tag: str, auth=Depends(require_write)):
        """
        Delete one lightweight tag.

        :param tag: Tag name to delete
        :type tag: str
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible success marker
        :rtype: dict
        """

        del auth
        get_api().delete_tag(tag=tag)
        return {"ok": True}

    @router.post("/merge")
    def merge(payload=Body(...), auth=Depends(require_write)):
        """
        Merge one source revision into a target branch.

        :param payload: Raw merge payload
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible merge result
        :rtype: dict
        """

        del auth
        data = _normalize_json_object(payload, "merge")
        result = get_api().merge(
            source_revision=_require_string_field(data, "source_revision", "merge"),
            target_revision=_optional_string_field(data, "target_revision", "merge"),
            parent_commit=_optional_string_field(data, "parent_commit", "merge"),
            commit_message=_optional_string_field(data, "commit_message", "merge"),
            commit_description=_optional_string_field(data, "commit_description", "merge"),
        )
        return encode_merge_result(result)

    @router.post("/reset-ref")
    def reset_ref(payload=Body(...), auth=Depends(require_write)):
        """
        Reset one branch ref to a target revision.

        :param payload: Raw reset-ref payload
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible commit metadata
        :rtype: dict
        """

        del auth
        data = _normalize_json_object(payload, "reset_ref")
        result = get_api().reset_ref(
            _require_string_field(data, "ref_name", "reset_ref"),
            to_revision=_require_string_field(data, "to_revision", "reset_ref"),
        )
        return encode_commit_info(result)

    @router.post("/delete-file")
    def delete_file(payload=Body(...), auth=Depends(require_write)):
        """
        Delete one file path through the public write API.

        :param payload: Raw delete-file payload
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible commit metadata
        :rtype: dict
        """

        del auth
        data = _normalize_json_object(payload, "delete_file")
        result = get_api().delete_file(
            _require_string_field(data, "path_in_repo", "delete_file"),
            revision=_optional_string_field(data, "revision", "delete_file"),
            commit_message=_optional_string_field(data, "commit_message", "delete_file"),
            commit_description=_optional_string_field(data, "commit_description", "delete_file"),
            parent_commit=_optional_string_field(data, "parent_commit", "delete_file"),
        )
        return encode_commit_info(result)

    @router.post("/delete-folder")
    def delete_folder(payload=Body(...), auth=Depends(require_write)):
        """
        Delete one folder subtree through the public write API.

        :param payload: Raw delete-folder payload
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible commit metadata
        :rtype: dict
        """

        del auth
        data = _normalize_json_object(payload, "delete_folder")
        result = get_api().delete_folder(
            _require_string_field(data, "path_in_repo", "delete_folder"),
            revision=_optional_string_field(data, "revision", "delete_folder"),
            commit_message=_optional_string_field(data, "commit_message", "delete_folder"),
            commit_description=_optional_string_field(data, "commit_description", "delete_folder"),
            parent_commit=_optional_string_field(data, "parent_commit", "delete_folder"),
        )
        return encode_commit_info(result)

    return router

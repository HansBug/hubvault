hubvault.server.auth
========================================================

.. currentmodule:: hubvault.server.auth

.. automodule:: hubvault.server.auth


AuthContext
-----------------------------------------------------

.. autoclass:: AuthContext
    :members: can_write,access,token


TokenAuthorizer
-----------------------------------------------------

.. autoclass:: TokenAuthorizer
    :members: __init__,resolve,require_write


parse\_request\_token
-----------------------------------------------------

.. autofunction:: parse_request_token


build\_read\_auth\_dependency
-----------------------------------------------------

.. autofunction:: build_read_auth_dependency


build\_write\_auth\_dependency
-----------------------------------------------------

.. autofunction:: build_write_auth_dependency



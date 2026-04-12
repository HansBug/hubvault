Service and ASGI Startup
========================

This guide covers the HTTP-facing runtime surfaces added on top of the local
repository core: the quick-start CLI, the import-friendly
:mod:`hubvault.server` module, and ASGI deployment through ``uvicorn`` or
``gunicorn``.

.. contents:: On this page
    :local:

Install the server extra
------------------------

The embedded HTTP server and bundled web UI are optional:

.. code-block:: shell

    pip install 'hubvault[api]'

If the extra is missing, importing ``hubvault`` still works. The dependency
error is raised only when you actually call a server feature such as
``hubvault serve`` or :func:`hubvault.server.create_app`.

CLI quick start
---------------

The fastest way to start the server is the CLI. The default mode is
``frontend``, which serves both the JSON API and the bundled browser UI on the
default port ``9472``.

.. code-block:: shell

    hubvault serve demo-repo \
        --init \
        --token-rw dev-token

That command creates the repository on first start and serves:

* browser UI: ``http://127.0.0.1:9472/``
* API root: ``http://127.0.0.1:9472/api/v1``

When you want only the JSON API, switch to ``api`` mode:

.. code-block:: shell

    hubvault serve demo-repo \
        --mode api \
        --init \
        --token-ro read-token \
        --token-rw write-token

In ``api`` mode, the generated OpenAPI docs remain available at ``/docs``.

Module entry point
------------------

The same runtime is exposed as ``python -m hubvault.server``:

.. code-block:: shell

    python -m hubvault.server demo-repo \
        --mode frontend \
        --init \
        --token-rw dev-token

This path is useful when you want explicit interpreter control or are embedding
the command in another Python-driven toolchain.

Import-friendly startup
-----------------------

The first-level :mod:`hubvault.server` module exposes the stable startup
surfaces directly:

.. code-block:: python

    from pathlib import Path

    from hubvault.server import SERVER_MODE_FRONTEND, ServerConfig, launch

    config = ServerConfig(
        repo_path=Path("demo-repo"),
        mode=SERVER_MODE_FRONTEND,
        token_rw=("dev-token",),
        init=True,
    )
    launch(config)

This is the recommended entry when your own Python process should control
startup rather than shelling out to the CLI.

ASGI deployment
---------------

The same application can be mounted by an ASGI server. The factory reads
``HUBVAULT_*`` environment variables when explicit parameters are not passed.

``uvicorn`` application-factory example:

.. code-block:: shell

    export HUBVAULT_REPO_PATH=./demo-repo
    export HUBVAULT_SERVE_MODE=frontend
    export HUBVAULT_TOKEN_RW=dev-token

    uvicorn --factory hubvault.server.asgi:create_app \
        --host 127.0.0.1 \
        --port 9472

``gunicorn`` application-factory example with an ASGI worker:

.. code-block:: shell

    export HUBVAULT_REPO_PATH=./demo-repo
    export HUBVAULT_SERVE_MODE=frontend
    export HUBVAULT_TOKEN_RW=dev-token

    gunicorn \
        --bind 127.0.0.1:9472 \
        --workers 2 \
        -k uvicorn.workers.UvicornWorker \
        'hubvault.server.asgi:create_app()'

Tokens and access model
-----------------------

At least one token is required. The server deliberately refuses anonymous
startup so local browsers, scripts, and remote clients all go through the same
auth path.

* ``--token-ro`` grants read-only API access
* ``--token-rw`` grants read-write API access
* multiple tokens may be supplied by repeating the option

Next step
---------

Continue with :doc:`../remote/index` when you want another Python process to
talk to the running server, or :doc:`../webui/index` for the bundled browser
frontend workflow.

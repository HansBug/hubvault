Bundled Web UI
==============

This guide focuses on the browser frontend that ships inside the Python
package and the standalone executable.

.. contents:: On this page
    :local:

What the web UI needs
---------------------

The browser UI is served by the same embedded HTTP runtime as the JSON API, so
it requires the server extra:

.. code-block:: shell

    pip install 'hubvault[api]'

Start the frontend mode with a read-write token:

.. code-block:: shell

    hubvault serve demo-repo --init --token-rw dev-token

Then open ``http://127.0.0.1:9472/``.

Login and direct token entry
----------------------------

The login page accepts a bearer token manually. For local ad-hoc access you can
also open a direct link such as:

.. code-block:: text

    http://127.0.0.1:9472/repo/overview?token=dev-token

The frontend consumes the query token, stores it in the current browser
session, and redirects to the clean route without leaving the token in the URL.

What the browser frontend provides
----------------------------------

The bundled UI is designed as a repository operator console. It currently
covers:

* overview page with README rendering, repository summary, and recent commits
* file tree with natural sorting, file-type icons, direct download actions, and
  dedicated file pages
* blob pages for text/code, Markdown, images, audio, video, and safe binary
  fallback handling
* commit detail pages with text diffs, media previews, and binary metadata
  cards only for unrenderable binary changes
* refs, history, storage overview, and upload workflows

Upload flow
-----------

The upload queue lives on a dedicated page reached from the Files view. You can
add files repeatedly, inspect the pending queue, let the UI generate a
placeholder commit message, or override it manually before submitting.

During large uploads the UI reports the active stage and byte progress so the
page does not look stalled while it performs dedup checks, chunk planning, and
streamed upload work.

Build and packaging flow
------------------------

The static files under ``hubvault/server/static/webui/`` are generated from the
``webui/`` source workspace:

.. code-block:: shell

    make webui_package

That command:

1. installs frontend dependencies when needed
2. builds ``webui/dist/``
3. syncs the built files into ``hubvault/server/static/webui/``

The release-oriented commands already depend on that sync step:

* ``make package`` bundles the synced frontend into sdist and wheel artifacts
* ``make build`` bundles the same frontend into the standalone executable

Verification
------------

Use the maintained frontend checks before releasing UI changes:

.. code-block:: shell

    make webui_test
    make webui_coverage
    make webui_e2e
    make webui_build

Next step
---------

Return to :doc:`../service/index` when you need deployment details, or to
:doc:`../remote/index` when you need the Python remote client rather than the
browser UI.

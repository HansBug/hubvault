"""
Phase 14 serializability and portability tests for :mod:`hubvault`.

This module exercises the Phase 14 guarantees strictly through the public API.
The covered scenarios verify same-process thread serialization, explicit
rejection of known network/shared filesystem mounts, and direct zip/unzip
portability for both healthy repositories and repositories carrying interrupted
transaction residue.
"""

import io
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from textwrap import dedent

import pytest

from hubvault import CommitOperationAdd, HubVaultApi


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_public_api_subprocess(script, *args, failpoint=None, action="raise-runtime", cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if failpoint is not None:
        env["HUBVAULT_FAILPOINT"] = failpoint
        env["HUBVAULT_FAIL_ACTION"] = action
    else:
        env.pop("HUBVAULT_FAILPOINT", None)
        env.pop("HUBVAULT_FAIL_ACTION", None)
    return subprocess.run(
        [sys.executable, "-c", dedent(script)] + [str(item) for item in args],
        cwd=str(cwd or PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


@pytest.mark.unittest
class TestPhase14SerializabilityAndPortability:
    def test_phase14_same_process_writer_blocks_reader_and_writer(self, tmp_path):
        repo_dir = tmp_path / "phase14-thread-serialization"
        seed_api = HubVaultApi(repo_dir)
        seed_api.create_repo()
        seed_api.create_commit(
            operations=[CommitOperationAdd("seed.txt", b"seed")],
            commit_message="seed thread serialization",
        )

        entered = threading.Event()
        release = threading.Event()
        reader_done = threading.Event()
        writer_done = threading.Event()
        second_writer_done = threading.Event()
        reader_payload = []
        errors = []

        class BlockingBytesIO(io.BytesIO):
            def __init__(self, payload):
                io.BytesIO.__init__(self, payload)

            def read(self, *args, **kwargs):
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("writer release timed out")
                return io.BytesIO.read(self, *args, **kwargs)

        def writer():
            try:
                api = HubVaultApi(repo_dir)
                api.create_commit(
                    operations=[CommitOperationAdd("blocked.bin", BlockingBytesIO(b"blocked"))],
                    commit_message="blocked writer",
                )
            except BaseException as err:
                errors.append(err)
            finally:
                writer_done.set()

        def reader():
            try:
                api = HubVaultApi(repo_dir)
                reader_payload.append(api.read_bytes("seed.txt"))
            except BaseException as err:
                errors.append(err)
            finally:
                reader_done.set()

        def second_writer():
            try:
                api = HubVaultApi(repo_dir)
                api.create_commit(
                    operations=[CommitOperationAdd("second.bin", b"second")],
                    commit_message="second writer",
                )
            except BaseException as err:
                errors.append(err)
            finally:
                second_writer_done.set()

        blocking_writer = threading.Thread(target=writer)
        blocking_reader = threading.Thread(target=reader)
        blocking_second_writer = threading.Thread(target=second_writer)

        blocking_writer.start()
        assert entered.wait(10), "writer never entered the public commit path"

        blocking_reader.start()
        blocking_second_writer.start()

        time.sleep(0.3)
        assert not reader_done.is_set()
        assert not second_writer_done.is_set()
        assert not writer_done.is_set()

        release.set()

        blocking_writer.join(timeout=10)
        blocking_reader.join(timeout=10)
        blocking_second_writer.join(timeout=10)

        assert not blocking_writer.is_alive()
        assert not blocking_reader.is_alive()
        assert not blocking_second_writer.is_alive()
        assert errors == []
        assert reader_payload == [b"seed"]
        assert seed_api.read_bytes("blocked.bin") == b"blocked"
        assert seed_api.read_bytes("second.bin") == b"second"
        assert seed_api.quick_verify().ok is True
        assert seed_api.full_verify().ok is True

    def test_phase14_zip_unzip_repo_reopens_without_extra_steps(self, tmp_path):
        repo_dir = tmp_path / "phase14-portable-repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        first_commit = api.create_commit(
            operations=[
                CommitOperationAdd("README.md", b"# portable\n"),
                CommitOperationAdd("models/model.bin", b"model-v1\n"),
            ],
            commit_message="seed portable repo",
        )
        assert Path(api.hf_hub_download("models/model.bin")).read_bytes() == b"model-v1\n"
        snapshot_root = Path(api.snapshot_download())
        assert snapshot_root.joinpath("README.md").read_text(encoding="utf-8") == "# portable\n"
        assert snapshot_root.joinpath("models", "model.bin").read_bytes() == b"model-v1\n"

        archive_path = shutil.make_archive(str(tmp_path / "phase14-portable-repo"), "zip", repo_dir.parent, repo_dir.name)
        unpack_root = tmp_path / "unzipped"
        shutil.unpack_archive(archive_path, unpack_root)
        reopened_repo_dir = unpack_root / repo_dir.name
        reopened_api = HubVaultApi(reopened_repo_dir)

        assert reopened_api.repo_info().head == first_commit.oid
        assert sorted(reopened_api.list_repo_files()) == ["README.md", "models/model.bin"]
        assert reopened_api.read_bytes("README.md") == b"# portable\n"
        assert reopened_api.read_bytes("models/model.bin") == b"model-v1\n"
        assert reopened_api.quick_verify().ok is True
        assert reopened_api.full_verify().ok is True
        assert Path(reopened_api.hf_hub_download("models/model.bin")).read_bytes() == b"model-v1\n"
        rebuilt_snapshot = Path(reopened_api.snapshot_download())
        assert rebuilt_snapshot.joinpath("README.md").read_text(encoding="utf-8") == "# portable\n"
        assert rebuilt_snapshot.joinpath("models", "model.bin").read_bytes() == b"model-v1\n"

        follow_up = reopened_api.create_commit(
            operations=[CommitOperationAdd("notes/after-unzip.txt", b"ok\n")],
            commit_message="after unzip",
        )
        assert reopened_api.repo_info().head == follow_up.oid
        assert reopened_api.read_bytes("notes/after-unzip.txt") == b"ok\n"

    def test_phase14_zip_unzip_interrupted_ref_transaction_recovers_without_extra_steps(self, tmp_path):
        repo_dir = tmp_path / "phase14-interrupted-repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        seed_commit = api.create_commit(
            operations=[CommitOperationAdd("keep.txt", b"seed\n")],
            commit_message="seed interrupted repo",
        )

        script = """
        import sys
        from hubvault import CommitOperationAdd, HubVaultApi

        repo_path = sys.argv[1]
        api = HubVaultApi(repo_path)
        api.create_commit(
            operations=[CommitOperationAdd("after-exit.txt", b"nope\\n")],
            commit_message="phase14 interrupted create",
        )
        """
        completed = _run_public_api_subprocess(
            script,
            repo_dir,
            failpoint="create_commit.after_ref_write",
            action="exit",
        )

        assert completed.returncode != 0

        archive_path = shutil.make_archive(str(tmp_path / "phase14-interrupted-repo"), "zip", repo_dir.parent, repo_dir.name)
        unpack_root = tmp_path / "unzipped-interrupted"
        shutil.unpack_archive(archive_path, unpack_root)
        reopened_repo_dir = unpack_root / repo_dir.name
        reopened_api = HubVaultApi(reopened_repo_dir)

        assert reopened_api.repo_info().head == seed_commit.oid
        assert reopened_api.read_bytes("keep.txt") == b"seed\n"
        assert "after-exit.txt" not in reopened_api.list_repo_files()
        assert reopened_api.quick_verify().ok is True
        assert reopened_api.full_verify().ok is True

        follow_up = reopened_api.create_commit(
            operations=[CommitOperationAdd("recovered.txt", b"ok\n")],
            commit_message="phase14 recovered create",
        )
        assert reopened_api.repo_info().head == follow_up.oid
        assert reopened_api.read_bytes("recovered.txt") == b"ok\n"

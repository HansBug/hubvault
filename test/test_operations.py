import io

import pytest

from hubvault.operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete


@pytest.mark.unittest
class TestOperations:
    def test_add_operation_from_bytes(self):
        operation = CommitOperationAdd.from_bytes("a.txt", b"alpha", content_type="text/plain")

        assert operation.path_in_repo == "a.txt"
        assert operation.data == b"alpha"
        assert operation.content_type == "text/plain"

    def test_add_operation_from_file(self, tmp_path):
        source = tmp_path / "source.bin"
        source.write_bytes(b"payload")

        operation = CommitOperationAdd.from_file("b.bin", str(source))

        assert operation.path_in_repo == "b.bin"
        assert operation.data == b"payload"
        assert operation.content_type is None

    def test_add_operation_from_fileobj(self):
        fileobj = io.BytesIO(b"streamed")

        operation = CommitOperationAdd.from_fileobj("c.bin", fileobj, content_type="application/octet-stream")

        assert operation.path_in_repo == "c.bin"
        assert operation.data == b"streamed"
        assert operation.content_type == "application/octet-stream"
        assert fileobj.tell() == len(b"streamed")

    def test_delete_and_copy_operations_store_public_fields(self):
        delete_operation = CommitOperationDelete("folder/old.txt")
        copy_operation = CommitOperationCopy("src/file.txt", "dst/file.txt")

        assert delete_operation.path_in_repo == "folder/old.txt"
        assert copy_operation.src_path_in_repo == "src/file.txt"
        assert copy_operation.path_in_repo == "dst/file.txt"


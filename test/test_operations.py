import io
import inspect

import pytest

from hubvault.operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete


@pytest.mark.unittest
class TestOperations:
    def test_add_operation_accepts_bytes_and_exposes_file_view(self):
        operation = CommitOperationAdd("a.txt", b"alpha")

        assert operation.path_in_repo == "a.txt"
        assert operation.path_or_fileobj == b"alpha"
        with operation.as_file() as fileobj:
            assert fileobj.read() == b"alpha"

    def test_add_operation_accepts_local_file_path(self, tmp_path):
        source = tmp_path / "source.bin"
        source.write_bytes(b"payload")

        operation = CommitOperationAdd("b.bin", source)

        assert operation.path_in_repo == "b.bin"
        assert operation.path_or_fileobj == str(source)
        with operation.as_file() as fileobj:
            assert fileobj.read() == b"payload"

    def test_add_operation_accepts_fileobj_and_restores_position(self):
        fileobj = io.BytesIO(b"streamed")
        fileobj.seek(3)

        operation = CommitOperationAdd("c.bin", fileobj)

        assert operation.path_in_repo == "c.bin"
        assert operation.path_or_fileobj is fileobj
        assert fileobj.tell() == 0
        with operation.as_file() as staged_file:
            assert staged_file.read() == b"streamed"
        assert fileobj.tell() == 0

        fileobj.seek(2)
        with operation.as_file() as staged_file:
            assert staged_file.read() == b"reamed"
        assert fileobj.tell() == 2

    def test_add_operation_rejects_missing_local_file(self, tmp_path):
        with pytest.raises(ValueError):
            CommitOperationAdd("missing.bin", tmp_path / "missing.bin")

    def test_add_operation_rejects_unsupported_source_type(self):
        with pytest.raises(ValueError):
            CommitOperationAdd("broken.bin", object())

    def test_add_operation_rejects_binary_stream_without_seek_and_tell_support(self):
        class BrokenBinaryStream(io.BytesIO):
            def tell(self):
                raise OSError("tell disabled")

        with pytest.raises(ValueError):
            CommitOperationAdd("broken.bin", BrokenBinaryStream(b"payload"))

    def test_public_commit_operation_signatures_match_hf_shape_without_no_op_flags(self):
        add_signature = inspect.signature(CommitOperationAdd)
        delete_signature = inspect.signature(CommitOperationDelete)
        copy_signature = inspect.signature(CommitOperationCopy)
        as_file_signature = inspect.signature(CommitOperationAdd.as_file)

        assert list(add_signature.parameters) == ["path_in_repo", "path_or_fileobj"]
        assert list(delete_signature.parameters) == ["path_in_repo", "is_folder"]
        assert list(copy_signature.parameters) == ["src_path_in_repo", "path_in_repo", "src_revision"]
        assert list(as_file_signature.parameters) == ["self"]

    def test_delete_and_copy_operations_follow_hf_style_public_fields(self):
        delete_operation = CommitOperationDelete("folder/")
        file_delete_operation = CommitOperationDelete("folder")
        copy_operation = CommitOperationCopy("src/file.txt", "dst/file.txt", src_revision="refs/pr/1")

        assert delete_operation.path_in_repo == "folder/"
        assert delete_operation.is_folder is True
        assert file_delete_operation.path_in_repo == "folder"
        assert file_delete_operation.is_folder is False
        assert copy_operation.src_path_in_repo == "src/file.txt"
        assert copy_operation.path_in_repo == "dst/file.txt"
        assert copy_operation.src_revision == "refs/pr/1"

    def test_delete_operation_rejects_invalid_is_folder_value(self):
        with pytest.raises(ValueError):
            CommitOperationDelete("folder", is_folder="nope")

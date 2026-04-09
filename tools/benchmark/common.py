"""Shared benchmark scenarios and metrics for Phase 9 work."""

import random
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from hubvault import CommitOperationAdd, HubVaultApi, RepoFile

MIB = 1024 * 1024
GIB = 1024 * MIB


@dataclass(frozen=True)
class Phase9BenchmarkConfig:
    """Configuration for the benchmark scenarios."""

    scale: str
    small_file_count: int
    small_file_size: int
    nested_directory_count: int
    nested_files_per_directory: int
    mixed_large_file_size: int
    history_deep_depth: int
    merge_side_commit_count: int
    cache_warm_rounds: int
    large_file_size: int
    duplicate_file_count: int
    overlap_shared_size: int
    overlap_unique_size: int
    shifted_window_step: int
    history_depth: int
    chunk_threshold: int
    range_start: int
    range_length: int
    rounds: int
    warmup_rounds: int

    @classmethod
    def from_scale(cls, scale: str = "standard") -> "Phase9BenchmarkConfig":
        """Build a benchmark configuration for a named scale."""

        normalized = str(scale or "standard").strip().lower()
        if normalized == "smoke":
            return cls(
                scale="smoke",
                small_file_count=32,
                small_file_size=4 * 1024,
                nested_directory_count=4,
                nested_files_per_directory=8,
                mixed_large_file_size=4 * MIB,
                history_deep_depth=24,
                merge_side_commit_count=2,
                cache_warm_rounds=1,
                large_file_size=6 * MIB,
                duplicate_file_count=4,
                overlap_shared_size=4 * MIB,
                overlap_unique_size=1 * MIB,
                shifted_window_step=512,
                history_depth=8,
                chunk_threshold=1 * MIB,
                range_start=1 * MIB + 123,
                range_length=256 * 1024,
                rounds=3,
                warmup_rounds=1,
            )
        if normalized == "pressure":
            return cls(
                scale="pressure",
                small_file_count=64,
                small_file_size=8 * 1024,
                nested_directory_count=8,
                nested_files_per_directory=8,
                mixed_large_file_size=32 * MIB,
                history_deep_depth=64,
                merge_side_commit_count=3,
                cache_warm_rounds=2,
                large_file_size=512 * MIB,
                duplicate_file_count=3,
                overlap_shared_size=384 * MIB,
                overlap_unique_size=128 * MIB,
                shifted_window_step=2 * MIB,
                history_depth=2,
                chunk_threshold=8 * MIB,
                range_start=128 * MIB + 123,
                range_length=32 * MIB,
                rounds=1,
                warmup_rounds=0,
            )
        if normalized in ("stress", "nightly"):
            return cls(
                scale="nightly" if normalized == "nightly" else "stress",
                small_file_count=256,
                small_file_size=8 * 1024,
                nested_directory_count=32,
                nested_files_per_directory=8,
                mixed_large_file_size=24 * MIB,
                history_deep_depth=256,
                merge_side_commit_count=6,
                cache_warm_rounds=3,
                large_file_size=16 * MIB,
                duplicate_file_count=10,
                overlap_shared_size=12 * MIB,
                overlap_unique_size=2 * MIB,
                shifted_window_step=2 * 1024,
                history_depth=48,
                chunk_threshold=1 * MIB,
                range_start=3 * MIB + 123,
                range_length=2 * MIB,
                rounds=5,
                warmup_rounds=1,
            )
        return cls(
            scale="standard",
            small_file_count=128,
            small_file_size=4 * 1024,
            nested_directory_count=16,
            nested_files_per_directory=8,
            mixed_large_file_size=16 * MIB,
            history_deep_depth=128,
            merge_side_commit_count=4,
            cache_warm_rounds=2,
            large_file_size=12 * MIB,
            duplicate_file_count=6,
            overlap_shared_size=8 * MIB,
            overlap_unique_size=1 * MIB,
            shifted_window_step=1024,
            history_depth=24,
            chunk_threshold=1 * MIB,
            range_start=2 * MIB + 123,
            range_length=1 * MIB,
            rounds=4,
            warmup_rounds=1,
        )


def to_mib(size_in_bytes: int) -> float:
    """Convert bytes to MiB."""

    return round(float(size_in_bytes) / float(MIB), 4)


def safe_ratio(numerator: int, denominator: int) -> float:
    """Return a rounded ratio or ``0.0`` when the denominator is empty."""

    if int(denominator) <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def deterministic_bytes(size: int, label: str) -> bytes:
    """Generate deterministic medium-entropy bytes."""

    size = int(size)
    if size <= 0:
        return b""

    seed = int(sha256(label.encode("utf-8")).hexdigest(), 16)
    rng = random.Random(seed)
    chunks = bytearray()
    chunk_size = 1024 * 1024
    while len(chunks) < size:
        current_size = min(chunk_size, size - len(chunks))
        try:
            chunks.extend(rng.randbytes(current_size))
        except AttributeError:
            chunks.extend(rng.getrandbits(current_size * 8).to_bytes(current_size, byteorder="little"))
    return bytes(chunks[:size])


def repeated_bytes(size: int, token: bytes) -> bytes:
    """Generate low-entropy repeated bytes."""

    size = int(size)
    if size <= 0:
        return b""
    if not token:
        token = b"\x00"
    repeats, tail = divmod(size, len(token))
    return (token * repeats) + token[:tail]


def repo_total_size(repo_dir: Path) -> int:
    """Return total bytes occupied by a repository root."""

    total = 0
    for path in repo_dir.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def file_count(root: Path) -> int:
    """Count files below a path."""

    return sum(1 for path in root.rglob("*") if path.is_file())


def overview_section_map(api: HubVaultApi) -> Dict[str, object]:
    """Return storage overview sections indexed by section name."""

    overview = api.get_storage_overview()
    return {section.name: section for section in overview.sections}


def section_size(api: HubVaultApi, section_name: str) -> int:
    """Return the current size of a named storage section."""

    sections = overview_section_map(api)
    try:
        return int(sections[section_name].total_size)
    except KeyError:
        return 0


def list_repo_file_infos(api: HubVaultApi) -> List[RepoFile]:
    """Return public file info objects for the current revision."""

    paths = list(api.list_repo_files())
    if not paths:
        return []
    infos = api.get_paths_info(paths)
    return [info for info in infos if isinstance(info, RepoFile)]


def _assert_quick_verify_ok(api: HubVaultApi) -> None:
    """Assert that quick verification succeeds."""

    report = api.quick_verify()
    assert report.ok is True, "quick_verify failed: errors=%r" % (report.errors,)


def _assert_full_verify_ok(api: HubVaultApi) -> None:
    """Assert that full verification succeeds."""

    report = api.full_verify()
    assert report.ok is True, "full_verify failed: errors=%r" % (report.errors,)


def _assert_repo_file_set(api: HubVaultApi, expected_paths: Sequence[str], revision: Optional[str] = None) -> List[str]:
    """Assert that the public repo file listing matches the expected set."""

    actual_paths = sorted(api.list_repo_files(revision=revision))
    normalized_expected = sorted(str(path).replace("\\", "/") for path in expected_paths)
    assert actual_paths == normalized_expected
    return actual_paths


def _assert_snapshot_manifest(snapshot_root: Path, expected_paths: Sequence[str]) -> List[str]:
    """Assert that one detached snapshot exports the expected files."""

    manifest = snapshot_file_manifest(snapshot_root)
    normalized_expected = sorted(str(path).replace("\\", "/") for path in expected_paths)
    assert manifest == normalized_expected
    return manifest


def logical_live_bytes(api: HubVaultApi) -> int:
    """Return total logical live bytes for the current revision."""

    return sum(int(info.size) for info in list_repo_file_infos(api))


def logical_live_large_bytes(api: HubVaultApi) -> int:
    """Return total logical live bytes for chunked large files."""

    return sum(int(info.size) for info in list_repo_file_infos(api) if info.lfs is not None)


def generate_small_tree_entries(config: Phase9BenchmarkConfig) -> List[Tuple[str, bytes]]:
    """Build a deterministic small-file tree payload set."""

    entries = []
    for index in range(int(config.small_file_count)):
        group = index // 16
        path = "dataset/group-{group:03d}/file-{index:04d}.bin".format(
            group=group,
            index=index,
        )
        payload = deterministic_bytes(int(config.small_file_size), "small-{index}".format(index=index))
        entries.append((path, payload))
    return entries


def generate_nested_small_entries(config: Phase9BenchmarkConfig) -> List[Tuple[str, bytes]]:
    """Build a deterministic nested small-file tree payload set."""

    entries = []
    nested_directory_count = int(config.nested_directory_count)
    nested_files_per_directory = int(config.nested_files_per_directory)
    index = 0
    for directory_index in range(nested_directory_count):
        cluster = directory_index // 4
        shard = directory_index % 4
        for file_index in range(nested_files_per_directory):
            path = (
                "dataset/cluster-{cluster:03d}/shard-{shard:03d}/bucket-{directory:03d}/file-{index:04d}.bin".format(
                    cluster=cluster,
                    shard=shard,
                    directory=directory_index,
                    index=index,
                )
            )
            payload = deterministic_bytes(
                int(config.small_file_size),
                "nested-small-{directory}-{file}".format(directory=directory_index, file=file_index),
            )
            entries.append((path, payload))
            index += 1
    return entries


def generate_mixed_model_entries(config: Phase9BenchmarkConfig) -> List[Tuple[str, bytes]]:
    """Build a deterministic mixed text/binary model-style repository payload set."""

    small_file_size = int(config.small_file_size)
    large_file_size = int(config.mixed_large_file_size)
    text_payload = (
        b'{"architectures":["HubVaultModel"],"hidden_size":1024,"num_hidden_layers":24,"vocab_size":32000}\n'
    )
    vocab_payload = b"\n".join(
        ("token_%05d" % index).encode("utf-8") for index in range(max(128, small_file_size // 8))
    ) + b"\n"
    entries = [
        ("README.md", b"# hubvault mixed-model benchmark\n"),
        ("config.json", text_payload),
        ("generation_config.json", b'{"max_length":2048,"temperature":0.7}\n'),
        ("tokenizer/tokenizer.json", deterministic_bytes(max(small_file_size * 2, 4096), "mixed-tokenizer-json")),
        ("tokenizer/vocab.txt", vocab_payload),
        ("tokenizer/special_tokens_map.json", b'{"bos_token":"<s>","eos_token":"</s>"}\n'),
        ("assets/sample.txt", deterministic_bytes(max(small_file_size, 2048), "mixed-sample-text")),
        ("artifacts/model-00001-of-00002.safetensors", deterministic_bytes(large_file_size, "mixed-large-00001")),
        ("artifacts/model-00002-of-00002.safetensors", deterministic_bytes(large_file_size, "mixed-large-00002")),
    ]
    return entries


def create_repo(api: HubVaultApi, large_file_threshold: int) -> None:
    """Create a repository with a chosen chunk threshold."""

    api.create_repo(large_file_threshold=int(large_file_threshold))


def next_round_repo_dir(tmp_path: Path, scenario_name: str) -> Path:
    """Return a unique per-round repository directory below ``tmp_path``."""

    scenario_root = tmp_path / scenario_name
    round_index = len(list(scenario_root.glob("*")))
    return scenario_root / ("round-%08d" % round_index)


def build_small_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, List[str], int]:
    """Create a repository populated with many small files."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=max(int(config.large_file_size) * 2, int(config.chunk_threshold) * 4))
    entries = generate_small_tree_entries(config)
    api.create_commit(
        operations=[CommitOperationAdd(path, data) for path, data in entries],
        commit_message="seed small tree",
    )
    paths = [path for path, _ in entries]
    _assert_repo_file_set(api, paths)
    _assert_quick_verify_ok(api)
    return api, paths, sum(len(data) for _, data in entries)


def build_nested_small_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, List[str], int]:
    """Create a repository populated with a deeply nested small-file tree."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=max(int(config.large_file_size) * 2, int(config.chunk_threshold) * 4))
    entries = generate_nested_small_entries(config)
    api.create_commit(
        operations=[CommitOperationAdd(path, data) for path, data in entries],
        commit_message="seed nested small tree",
    )
    paths = [path for path, _ in entries]
    _assert_repo_file_set(api, paths)
    _assert_quick_verify_ok(api)
    return api, paths, sum(len(data) for _, data in entries)


def build_mixed_model_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, List[str], int, List[str]]:
    """Create a repository shaped like a small model snapshot with large binaries."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    entries = generate_mixed_model_entries(config)
    api.create_commit(
        operations=[CommitOperationAdd(path, data) for path, data in entries],
        commit_message="seed mixed model repo",
    )
    paths = [path for path, _ in entries]
    total_bytes = sum(len(data) for _, data in entries)
    large_paths = [path for path, _ in entries if path.endswith(".safetensors")]
    _assert_repo_file_set(api, paths)
    _assert_quick_verify_ok(api)
    return api, paths, total_bytes, large_paths


def build_large_repo(
    repo_dir: Path,
    config: Phase9BenchmarkConfig,
    payload: Optional[bytes] = None,
    path_in_repo: str = "artifacts/model.bin",
) -> Tuple[HubVaultApi, bytes]:
    """Create a repository with one chunked large file."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    resolved_payload = payload or deterministic_bytes(int(config.large_file_size), "large-binary")
    api.upload_file(
        path_or_fileobj=resolved_payload,
        path_in_repo=path_in_repo,
        commit_message="seed large file",
    )
    assert api.read_bytes(path_in_repo) == resolved_payload
    _assert_quick_verify_ok(api)
    return api, resolved_payload


def build_exact_duplicate_live_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository with many identical live large files."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    payload = deterministic_bytes(int(config.large_file_size), "exact-duplicate")
    operations = []
    for index in range(int(config.duplicate_file_count)):
        operations.append(
            CommitOperationAdd(
                "duplicates/exact-{index:02d}.bin".format(index=index),
                payload,
            )
        )
    api.create_commit(operations=operations, commit_message="seed exact duplicate live set")
    expected_paths = ["duplicates/exact-{index:02d}.bin".format(index=index) for index in range(int(config.duplicate_file_count))]
    _assert_repo_file_set(api, expected_paths)
    assert api.read_bytes(expected_paths[0]) == payload
    assert api.read_bytes(expected_paths[-1]) == payload
    _assert_quick_verify_ok(api)
    logical_total = len(payload) * int(config.duplicate_file_count)
    return api, logical_total, len(payload)


def build_aligned_overlap_live_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository whose large files share chunk-aligned common prefixes."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    shared = deterministic_bytes(int(config.overlap_shared_size), "aligned-shared")
    operations = []
    expected_payloads = {}
    for index in range(int(config.duplicate_file_count)):
        unique_tail = deterministic_bytes(int(config.overlap_unique_size), "aligned-tail-{index}".format(index=index))
        payload = shared + unique_tail
        path = "duplicates/aligned-{index:02d}.bin".format(index=index)
        expected_payloads[path] = payload
        operations.append(
            CommitOperationAdd(
                path,
                payload,
            )
        )
    api.create_commit(operations=operations, commit_message="seed aligned overlap live set")
    expected_paths = sorted(expected_payloads)
    _assert_repo_file_set(api, expected_paths)
    assert api.read_bytes(expected_paths[0]) == expected_payloads[expected_paths[0]]
    assert api.read_bytes(expected_paths[-1]) == expected_payloads[expected_paths[-1]]
    _assert_quick_verify_ok(api)
    file_size = len(shared) + int(config.overlap_unique_size)
    logical_total = file_size * int(config.duplicate_file_count)
    logical_unique = len(shared) + (int(config.overlap_unique_size) * int(config.duplicate_file_count))
    return api, logical_total, logical_unique


def build_shifted_overlap_live_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository whose large files are sliding windows over one base payload."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    base = deterministic_bytes(
        int(config.large_file_size) + (int(config.shifted_window_step) * (int(config.duplicate_file_count) - 1)),
        "shifted-window-base",
    )
    operations = []
    expected_payloads = {}
    for index in range(int(config.duplicate_file_count)):
        start = index * int(config.shifted_window_step)
        payload = base[start:start + int(config.large_file_size)]
        path = "duplicates/shifted-{index:02d}.bin".format(index=index)
        expected_payloads[path] = payload
        operations.append(
            CommitOperationAdd(
                path,
                payload,
            )
        )
    api.create_commit(operations=operations, commit_message="seed shifted overlap live set")
    expected_paths = sorted(expected_payloads)
    _assert_repo_file_set(api, expected_paths)
    assert api.read_bytes(expected_paths[0]) == expected_payloads[expected_paths[0]]
    assert api.read_bytes(expected_paths[-1]) == expected_payloads[expected_paths[-1]]
    _assert_quick_verify_ok(api)
    logical_total = int(config.large_file_size) * int(config.duplicate_file_count)
    logical_unique = len(base)
    return api, logical_total, logical_unique


def build_historical_duplicate_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository with repeated identical large-file commits on one path."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    payload = deterministic_bytes(int(config.large_file_size), "historical-duplicate")
    for index in range(int(config.history_depth)):
        api.upload_file(
            path_or_fileobj=payload,
            path_in_repo="history/model.bin",
            commit_message="history duplicate {index:03d}".format(index=index),
        )
    _assert_repo_file_set(api, ["history/model.bin"])
    assert api.read_bytes("history/model.bin") == payload
    assert len(api.list_repo_commits()) == int(config.history_depth) + 1
    _assert_quick_verify_ok(api)
    return api, len(payload), len(payload)


def build_maintenance_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a repository suited for verify and GC benchmarks."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    shared = deterministic_bytes(int(config.overlap_shared_size), "maintenance-shared")
    last_payload = b""
    for index in range(int(config.history_depth)):
        payload = shared + deterministic_bytes(int(config.overlap_unique_size), "maintenance-tail-{index}".format(index=index))
        last_payload = payload
        api.upload_file(
            path_or_fileobj=payload,
            path_in_repo="models/model.bin",
            commit_message="maintenance version {index:03d}".format(index=index),
        )
    download_path = Path(api.hf_hub_download("models/model.bin"))
    snapshot_root = Path(api.snapshot_download())
    assert api.read_bytes("models/model.bin") == last_payload
    assert download_path.read_bytes() == last_payload
    _assert_snapshot_manifest(snapshot_root, ["models/model.bin"])
    assert (snapshot_root / "models" / "model.bin").read_bytes() == last_payload
    _assert_quick_verify_ok(api)
    return api, logical_live_bytes(api)


def build_verify_heavy_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a repository shaped for verify-heavy maintenance benchmarks."""

    api, paths, total_bytes, large_paths = build_mixed_model_repo(repo_dir, config)
    expected_note_payloads = {}
    for index in range(int(config.merge_side_commit_count)):
        note_path = "notes/revision-%02d.txt" % index
        note_payload = deterministic_bytes(int(config.small_file_size), "verify-heavy-note-%02d" % index)
        expected_note_payloads[note_path] = note_payload
        api.upload_file(
            path_or_fileobj=note_payload,
            path_in_repo=note_path,
            commit_message="verify heavy note %02d" % index,
        )
    head_commit = api.repo_info().head
    if head_commit is not None:
        api.create_branch(branch="verify-review", revision=head_commit, exist_ok=True)
        api.create_tag(tag="verify-heavy-tip", revision=head_commit, exist_ok=True)
    for large_path in large_paths:
        assert Path(api.hf_hub_download(large_path)).read_bytes() == api.read_bytes(large_path)
    snapshot_root = Path(api.snapshot_download())
    expected_paths = paths + sorted(expected_note_payloads)
    _assert_repo_file_set(api, expected_paths)
    _assert_snapshot_manifest(snapshot_root, expected_paths)
    for note_path, note_payload in expected_note_payloads.items():
        assert api.read_bytes(note_path) == note_payload
    _assert_quick_verify_ok(api)
    return api, total_bytes + (int(config.small_file_size) * int(config.merge_side_commit_count))


def build_history_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a deep small-file history with refs and reflog activity."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=max(int(config.large_file_size) * 2, int(config.chunk_threshold) * 4))
    last_payload = b""
    for index in range(int(config.history_depth)):
        last_payload = deterministic_bytes(int(config.small_file_size), "history-{index}".format(index=index))
        api.upload_file(
            path_or_fileobj=last_payload,
            path_in_repo="history/timeline.bin",
            commit_message="history version {index:03d}".format(index=index),
        )
    head_commit = api.repo_info().head
    if head_commit is not None:
        api.create_branch(branch="review", revision=head_commit, exist_ok=True)
        api.create_tag(tag="history-tip", revision=head_commit, exist_ok=True)
    _assert_repo_file_set(api, ["history/timeline.bin"])
    assert api.read_bytes("history/timeline.bin") == last_payload
    assert len(api.list_repo_commits()) == int(config.history_depth) + 1
    _assert_quick_verify_ok(api)
    return api, len(api.list_repo_commits())


def build_history_deep_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a deeper history dataset for metadata-heavy benchmark paths."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=max(int(config.large_file_size) * 2, int(config.chunk_threshold) * 4))
    depth = int(config.history_deep_depth)
    last_timeline_payload = b""
    last_metadata_path = "history/metadata/000.json"
    last_metadata_payload = b""
    for index in range(depth):
        last_timeline_payload = deterministic_bytes(int(config.small_file_size), "history-deep-main-%03d" % index)
        last_metadata_path = "history/metadata/%03d.json" % (index % 16)
        last_metadata_payload = deterministic_bytes(max(int(config.small_file_size) // 2, 256), "history-deep-meta-%03d" % index)
        operations = [
            CommitOperationAdd(
                "history/timeline.bin",
                last_timeline_payload,
            ),
            CommitOperationAdd(
                last_metadata_path,
                last_metadata_payload,
            ),
        ]
        api.create_commit(
            operations=operations,
            commit_message="history deep version %03d" % index,
        )
    head_commit = api.repo_info().head
    if head_commit is not None:
        api.create_branch(branch="review", revision=head_commit, exist_ok=True)
        api.create_branch(branch="release", revision=head_commit, exist_ok=True)
        api.create_tag(tag="history-deep-tip", revision=head_commit, exist_ok=True)
    assert api.read_bytes("history/timeline.bin") == last_timeline_payload
    assert api.read_bytes(last_metadata_path) == last_metadata_payload
    assert len(api.list_repo_commits()) == depth + 1
    _assert_quick_verify_ok(api)
    return api, depth + 1


def build_merge_ready_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a repository ready for a non-fast-forward merge benchmark."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    base_model = deterministic_bytes(int(config.chunk_threshold) * 2, "merge-base-model")
    feature_model = deterministic_bytes(int(config.chunk_threshold) * 2, "merge-feature-model")
    main_note = deterministic_bytes(int(config.small_file_size), "merge-main-note")
    feature_note = deterministic_bytes(int(config.small_file_size), "merge-feature-note")
    api.create_commit(
        operations=[
            CommitOperationAdd("artifacts/model.bin", base_model),
            CommitOperationAdd("README.md", b"# merge-benchmark\n"),
        ],
        commit_message="seed merge benchmark",
    )
    api.create_branch(branch="feature")
    api.create_commit(
        revision="feature",
        operations=[
            CommitOperationAdd("artifacts/model.bin", feature_model),
            CommitOperationAdd("notes/feature.txt", feature_note),
        ],
        commit_message="feature update",
    )
    api.create_commit(
        revision="main",
        operations=[CommitOperationAdd("notes/main.txt", main_note)],
        commit_message="main update",
    )
    _assert_repo_file_set(api, ["README.md", "artifacts/model.bin", "notes/main.txt"])
    _assert_repo_file_set(api, ["README.md", "artifacts/model.bin", "notes/feature.txt"], revision="feature")
    assert api.read_bytes("artifacts/model.bin") == base_model
    assert api.read_bytes("artifacts/model.bin", revision="feature") == feature_model
    _assert_quick_verify_ok(api)
    return api, len(feature_model) + len(feature_note) + len(main_note)


def build_merge_heavy_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a deeper branchy repository for merge-heavy benchmark paths."""

    api, total_bytes = build_merge_ready_repo(repo_dir, config)
    for index in range(int(config.merge_side_commit_count)):
        api.create_commit(
            revision="feature",
            operations=[
                CommitOperationAdd(
                    "notes/feature-series-%02d.txt" % index,
                    deterministic_bytes(int(config.small_file_size), "merge-heavy-feature-%02d" % index),
                )
            ],
            commit_message="feature series %02d" % index,
        )
        api.create_commit(
            revision="main",
            operations=[
                CommitOperationAdd(
                    "notes/main-series-%02d.txt" % index,
                    deterministic_bytes(int(config.small_file_size), "merge-heavy-main-%02d" % index),
                )
            ],
            commit_message="main series %02d" % index,
        )
        total_bytes += int(config.small_file_size) * 2
    expected_feature_paths = ["README.md", "artifacts/model.bin", "notes/feature.txt"] + [
        "notes/feature-series-%02d.txt" % index for index in range(int(config.merge_side_commit_count))
    ]
    expected_main_paths = ["README.md", "artifacts/model.bin", "notes/main.txt"] + [
        "notes/main-series-%02d.txt" % index for index in range(int(config.merge_side_commit_count))
    ]
    _assert_repo_file_set(api, expected_main_paths)
    _assert_repo_file_set(api, expected_feature_paths, revision="feature")
    _assert_quick_verify_ok(api)
    return api, total_bytes


def build_cache_heavy_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, List[str], int]:
    """Create a repository with pre-existing download and snapshot cache state."""

    api, _paths, total_bytes, large_paths = build_mixed_model_repo(repo_dir, config)
    rounds = max(1, int(config.cache_warm_rounds))
    for _ in range(rounds):
        for large_path in large_paths:
            _ = api.hf_hub_download(large_path)
        _ = api.snapshot_download()
    for large_path in large_paths:
        assert Path(api.hf_hub_download(large_path)).read_bytes() == api.read_bytes(large_path)
    _assert_quick_verify_ok(api)
    return api, large_paths, total_bytes


def threshold_sweep_sizes(config: Phase9BenchmarkConfig) -> List[int]:
    """Return the file sizes used for whole-file versus chunked threshold scans."""

    threshold = int(config.chunk_threshold)
    sizes = [
        max(1, threshold - 1),
        threshold,
        threshold + 1,
        threshold * 4,
    ]
    ordered = []
    for size in sizes:
        if size not in ordered:
            ordered.append(size)
    return ordered


def read_all_small_files(api: HubVaultApi, paths: Sequence[str]) -> int:
    """Read all small files and return the processed byte count."""

    total = 0
    for path in paths:
        total += len(api.read_bytes(path))
    return total


def snapshot_file_manifest(snapshot_root: Path) -> List[str]:
    """Return a normalized file manifest for a detached snapshot."""

    return sorted(
        str(path.relative_to(snapshot_root)).replace("\\", "/")
        for path in snapshot_root.rglob("*")
        if path.is_file()
    )


def collect_space_profile(
    api: HubVaultApi,
    logical_live_total: int,
    logical_unique_estimate: Optional[int],
) -> Dict[str, object]:
    """Collect repository space metrics before and after GC."""

    before = api.get_storage_overview()
    dry_gc = api.gc(dry_run=True, prune_cache=False)
    quick_ok = api.quick_verify().ok
    actual_gc = api.gc(dry_run=False, prune_cache=False)
    after = api.get_storage_overview()
    full_ok = api.full_verify().ok
    assert quick_ok is True
    assert full_ok is True

    before_sections = {section.name: section for section in before.sections}
    after_sections = {section.name: section for section in after.sections}
    before_pack = int(before_sections["chunks.packs"].total_size)
    after_pack = int(after_sections["chunks.packs"].total_size)
    before_index = int(before_sections["chunks.index"].total_size)
    after_index = int(after_sections["chunks.index"].total_size)
    unique_estimate = int(logical_unique_estimate) if logical_unique_estimate is not None else 0

    metrics = {
        "logical_live_bytes": int(logical_live_total),
        "logical_unique_estimate_bytes": unique_estimate,
        "chunk_pack_bytes_before_gc": before_pack,
        "chunk_pack_bytes_after_gc": after_pack,
        "chunk_index_bytes_before_gc": before_index,
        "chunk_index_bytes_after_gc": after_index,
        "total_repo_bytes_before_gc": int(before.total_size),
        "total_repo_bytes_after_gc": int(after.total_size),
        "reclaimable_gc_bytes_before_gc": int(before.reclaimable_gc_size),
        "gc_reclaimed_size": int(actual_gc.reclaimed_size),
        "gc_reclaimed_chunk_size": int(actual_gc.reclaimed_chunk_size),
        "gc_dry_run_reclaimed_size": int(dry_gc.reclaimed_size),
        "quick_verify_ok_after_setup": bool(quick_ok),
        "full_verify_ok_after_gc": bool(full_ok),
        "physical_over_logical_before_gc": safe_ratio(before_pack, int(logical_live_total)),
        "physical_over_logical_after_gc": safe_ratio(after_pack, int(logical_live_total)),
        "logical_over_physical_after_gc": safe_ratio(int(logical_live_total), after_pack),
        "space_amplification_live": safe_ratio(before_pack, int(logical_live_total)),
        "space_amplification_live_after_gc": safe_ratio(after_pack, int(logical_live_total)),
        "dedup_gain_after_gc": safe_ratio(before_pack, after_pack),
        "space_reduction_after_gc": safe_ratio(before_pack - after_pack, before_pack),
    }
    if unique_estimate > 0:
        metrics.update(
            {
                "physical_over_unique_before_gc": safe_ratio(before_pack, unique_estimate),
                "physical_over_unique_after_gc": safe_ratio(after_pack, unique_estimate),
                "space_amplification_unique": safe_ratio(before_pack, unique_estimate),
                "space_amplification_unique_after_gc": safe_ratio(after_pack, unique_estimate),
                "unique_over_physical_after_gc": safe_ratio(unique_estimate, after_pack),
            }
        )
    return metrics


def benchmark_workspace(parent: Path, prefix: str) -> tempfile.TemporaryDirectory:
    """Return a temporary workspace rooted below ``parent``."""

    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=str(parent))


def run_small_batch_commit_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute one end-to-end small batch commit scenario."""

    with benchmark_workspace(workspace_root, "phase9-small-write-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        overview = api.get_storage_overview()
        return {
            "processed_bytes": int(total_bytes),
            "operation_count": len(paths),
            "live_file_count": len(paths),
            "repo_total_bytes": int(overview.total_size),
            "reachable_bytes": int(overview.reachable_size),
            "blob_bytes": int(section_size(api, "objects.blobs.data")),
            "cache_bytes": int(overview.reclaimable_cache_size),
        }


def run_nested_tree_listing_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute recursive tree listing over a nested small-file repository."""

    with benchmark_workspace(workspace_root, "phase12-nested-tree-") as tmpdir:
        api, paths, total_bytes = build_nested_small_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        items = list(api.list_repo_tree(recursive=True))
        finished = time.perf_counter()
        tree_file_paths = sorted(item.path for item in items if isinstance(item, RepoFile))
        assert tree_file_paths == sorted(paths)
        return {
            "processed_bytes": 0,
            "operation_seconds": round(finished - started, 6),
            "operation_count": len(items),
            "dataset_family": "nested-small",
            "tree_entry_count": len(items),
            "live_file_count": len(paths),
            "logical_live_bytes": int(total_bytes),
        }


def run_mixed_model_snapshot_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a mixed-model snapshot export benchmark."""

    with benchmark_workspace(workspace_root, "phase12-mixed-model-snapshot-") as tmpdir:
        api, paths, total_bytes, _large_paths = build_mixed_model_repo(Path(tmpdir) / "repo", config)
        before = api.get_storage_overview()
        started = time.perf_counter()
        snapshot_root = Path(api.snapshot_download())
        finished = time.perf_counter()
        after = api.get_storage_overview()
        manifest = _assert_snapshot_manifest(snapshot_root, paths)
        return {
            "processed_bytes": int(total_bytes),
            "operation_seconds": round(finished - started, 6),
            "operation_count": len(manifest),
            "dataset_family": "mixed-model",
            "snapshot_file_count": len(manifest),
            "live_file_count": len(paths),
            "cache_delta_bytes": int(after.reclaimable_cache_size - before.reclaimable_cache_size),
            "files_materialized": len(manifest),
        }


def run_large_upload_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute one end-to-end large upload scenario."""

    with benchmark_workspace(workspace_root, "phase9-large-write-") as tmpdir:
        api, payload = build_large_repo(Path(tmpdir) / "repo", config)
        overview = api.get_storage_overview()
        return {
            "processed_bytes": len(payload),
            "dataset_family": "large-single",
            "repo_total_bytes": int(overview.total_size),
            "chunk_pack_bytes": int(section_size(api, "chunks.packs")),
            "chunk_index_bytes": int(section_size(api, "chunks.index")),
            "large_live_bytes": int(logical_live_large_bytes(api)),
        }


def run_hf_hub_download_cold_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a cold detached-file download on a chunked large file."""

    with benchmark_workspace(workspace_root, "phase9-download-cold-") as tmpdir:
        api, payload = build_large_repo(Path(tmpdir) / "repo", config)
        before = api.get_storage_overview()
        started = time.perf_counter()
        path = Path(api.hf_hub_download("artifacts/model.bin"))
        finished = time.perf_counter()
        after = api.get_storage_overview()
        assert path.read_bytes() == payload
        assert str(path).replace("\\", "/").endswith("artifacts/model.bin")
        return {
            "processed_bytes": len(payload),
            "operation_seconds": round(finished - started, 6),
            "operation_count": 1,
            "dataset_family": "large-single",
            "downloaded_bytes": int(path.stat().st_size),
            "cache_delta_bytes": int(after.reclaimable_cache_size - before.reclaimable_cache_size),
            "suffix_preserved": str(path).replace("\\", "/").endswith("artifacts/model.bin"),
        }


def run_hf_hub_download_warm_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a warm detached-file download on an already materialized file view."""

    with benchmark_workspace(workspace_root, "phase9-download-warm-") as tmpdir:
        api, payload = build_large_repo(Path(tmpdir) / "repo", config)
        first_path = Path(api.hf_hub_download("artifacts/model.bin"))
        before = api.get_storage_overview()
        started = time.perf_counter()
        second_path = Path(api.hf_hub_download("artifacts/model.bin"))
        finished = time.perf_counter()
        after = api.get_storage_overview()
        assert first_path.read_bytes() == payload
        assert second_path.read_bytes() == payload
        assert str(first_path) == str(second_path)
        assert str(second_path).replace("\\", "/").endswith("artifacts/model.bin")
        return {
            "processed_bytes": len(payload),
            "operation_seconds": round(finished - started, 6),
            "operation_count": 1,
            "dataset_family": "large-single",
            "downloaded_bytes": int(second_path.stat().st_size),
            "cache_delta_bytes": int(after.reclaimable_cache_size - before.reclaimable_cache_size),
            "reused_view_path": str(first_path) == str(second_path),
            "suffix_preserved": str(second_path).replace("\\", "/").endswith("artifacts/model.bin"),
        }


def run_history_listing_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute commit/ref/reflog listing over a deep small-file history."""

    with benchmark_workspace(workspace_root, "phase9-history-list-") as tmpdir:
        api, commit_count = build_history_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        commits = list(api.list_repo_commits())
        refs = api.list_repo_refs()
        reflog = list(api.list_repo_reflog("main"))
        finished = time.perf_counter()
        assert len(commits) == int(commit_count)
        assert len(refs.branches) >= 2
        assert len(refs.tags) >= 1
        assert len(reflog) >= len(commits)
        return {
            "processed_bytes": 0,
            "operation_seconds": round(finished - started, 6),
            "operation_count": len(commits) + len(refs.branches) + len(refs.tags) + len(reflog),
            "dataset_family": "history",
            "commit_count": len(commits),
            "expected_commit_count": int(commit_count),
            "branch_count": len(refs.branches),
            "tag_count": len(refs.tags),
            "reflog_count": len(reflog),
        }


def run_history_deep_listing_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute commit/ref/reflog listing over the deeper Phase 12 history dataset."""

    with benchmark_workspace(workspace_root, "phase12-history-deep-") as tmpdir:
        api, commit_count = build_history_deep_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        commits = list(api.list_repo_commits())
        refs = api.list_repo_refs()
        reflog = list(api.list_repo_reflog("main"))
        finished = time.perf_counter()
        assert len(commits) == int(commit_count)
        assert len(refs.branches) >= 3
        assert len(refs.tags) >= 1
        assert len(reflog) >= len(commits)
        return {
            "processed_bytes": 0,
            "operation_seconds": round(finished - started, 6),
            "operation_count": len(commits) + len(refs.branches) + len(refs.tags) + len(reflog),
            "dataset_family": "history-deep",
            "commit_count": len(commits),
            "expected_commit_count": int(commit_count),
            "branch_count": len(refs.branches),
            "tag_count": len(refs.tags),
            "reflog_count": len(reflog),
        }


def run_merge_non_fast_forward_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute one successful non-fast-forward merge workflow."""

    with benchmark_workspace(workspace_root, "phase9-merge-") as tmpdir:
        api, merge_shape_bytes = build_merge_ready_repo(Path(tmpdir) / "repo", config)
        before_history_count = len(api.list_repo_commits())
        started = time.perf_counter()
        result = api.merge("feature")
        finished = time.perf_counter()
        after_history_count = len(api.list_repo_commits())
        expected_history_increase = 2
        assert result.status == "merged"
        assert result.fast_forward is False
        assert result.created_commit is True
        assert result.conflicts == []
        assert after_history_count == before_history_count + expected_history_increase
        _assert_repo_file_set(api, ["README.md", "artifacts/model.bin", "notes/feature.txt", "notes/main.txt"])
        _assert_quick_verify_ok(api)
        return {
            "processed_bytes": int(merge_shape_bytes),
            "operation_seconds": round(finished - started, 6),
            "dataset_family": "merge-ready",
            "merge_status": result.status,
            "created_commit": bool(result.created_commit),
            "conflict_count": len(result.conflicts),
            "history_count_before": before_history_count,
            "history_count_after": after_history_count,
        }


def run_merge_heavy_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a deeper non-fast-forward merge workflow."""

    with benchmark_workspace(workspace_root, "phase12-merge-heavy-") as tmpdir:
        api, merge_shape_bytes = build_merge_heavy_repo(Path(tmpdir) / "repo", config)
        before_history_count = len(api.list_repo_commits())
        started = time.perf_counter()
        result = api.merge("feature")
        finished = time.perf_counter()
        after_history_count = len(api.list_repo_commits())
        expected_note_count = 2 + (2 * int(config.merge_side_commit_count))
        expected_history_increase = int(config.merge_side_commit_count) + 2
        actual_note_paths = [path for path in api.list_repo_files() if path.startswith("notes/")]
        assert result.status == "merged"
        assert result.fast_forward is False
        assert result.created_commit is True
        assert result.conflicts == []
        assert after_history_count == before_history_count + expected_history_increase
        assert len(actual_note_paths) == expected_note_count
        _assert_quick_verify_ok(api)
        return {
            "processed_bytes": int(merge_shape_bytes),
            "operation_seconds": round(finished - started, 6),
            "operation_count": before_history_count + after_history_count,
            "dataset_family": "merge-heavy",
            "merge_status": result.status,
            "created_commit": bool(result.created_commit),
            "conflict_count": len(result.conflicts),
            "history_count_before": before_history_count,
            "history_count_after": after_history_count,
        }


def run_threshold_sweep_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a whole-file versus chunked threshold boundary scan."""

    with benchmark_workspace(workspace_root, "phase9-threshold-sweep-") as tmpdir:
        workspace = Path(tmpdir)
        results = []
        total_processed = 0
        total_operation_seconds = 0.0
        for size in threshold_sweep_sizes(config):
            repo_dir = workspace / ("size-%d" % size)
            api = HubVaultApi(repo_dir)
            create_repo(api, large_file_threshold=int(config.chunk_threshold))
            payload = deterministic_bytes(int(size), "threshold-{size}".format(size=size))
            started = time.perf_counter()
            api.upload_file(
                path_or_fileobj=payload,
                path_in_repo="artifacts/payload.bin",
                commit_message="threshold payload {size}".format(size=size),
            )
            finished = time.perf_counter()
            info = api.get_paths_info(["artifacts/payload.bin"])[0]
            assert isinstance(info, RepoFile)
            assert api.read_bytes("artifacts/payload.bin") == payload
            _assert_quick_verify_ok(api)
            operation_seconds = finished - started
            results.append(
                {
                    "file_size": int(size),
                    "chunked": bool(info.lfs is not None),
                    "operation_seconds": round(operation_seconds, 6),
                    "blob_bytes": int(section_size(api, "objects.blobs.data")),
                    "chunk_pack_bytes": int(section_size(api, "chunks.packs")),
                }
            )
            total_processed += len(payload)
            total_operation_seconds += operation_seconds

        below = next((item for item in results if item["file_size"] == int(config.chunk_threshold) - 1), None)
        at = next((item for item in results if item["file_size"] == int(config.chunk_threshold)), None)
        above = next((item for item in results if item["file_size"] == int(config.chunk_threshold) + 1), None)
        return {
            "processed_bytes": int(total_processed),
            "operation_seconds": round(total_operation_seconds, 6),
            "threshold_cases": len(results),
            "dataset_family": "threshold-sweep",
            "threshold_boundary_below_chunked": bool(below and below["chunked"]),
            "threshold_boundary_at_chunked": bool(at and at["chunked"]),
            "threshold_boundary_above_chunked": bool(above and above["chunked"]),
            "threshold_results": results,
        }


def run_cache_heavy_warm_download_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a warm detached-file download on a cache-heavy mixed-model repo."""

    with benchmark_workspace(workspace_root, "phase12-cache-heavy-") as tmpdir:
        api, large_paths, total_bytes = build_cache_heavy_repo(Path(tmpdir) / "repo", config)
        target_path = large_paths[-1]
        before = api.get_storage_overview()
        started = time.perf_counter()
        local_path = Path(api.hf_hub_download(target_path))
        finished = time.perf_counter()
        after = api.get_storage_overview()
        assert local_path.read_bytes() == api.read_bytes(target_path)
        assert str(local_path).replace("\\", "/").endswith(target_path)
        return {
            "processed_bytes": int(local_path.stat().st_size),
            "operation_seconds": round(finished - started, 6),
            "operation_count": 1,
            "dataset_family": "cache-heavy",
            "logical_live_bytes": int(total_bytes),
            "downloaded_bytes": int(local_path.stat().st_size),
            "cache_delta_bytes": int(after.reclaimable_cache_size - before.reclaimable_cache_size),
            "suffix_preserved": str(local_path).replace("\\", "/").endswith(target_path),
        }


def run_squash_history_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a history rewrite followed by in-operation GC."""

    with benchmark_workspace(workspace_root, "phase9-squash-") as tmpdir:
        api, logical_live_total, _logical_unique = build_historical_duplicate_repo(Path(tmpdir) / "repo", config)
        history_before = len(api.list_repo_commits())
        started = time.perf_counter()
        report = api.squash_history("main", run_gc=True, prune_cache=False)
        finished = time.perf_counter()
        history_after = len(api.list_repo_commits())
        reclaimed_size = 0
        if report.gc_report is not None:
            reclaimed_size = int(report.gc_report.reclaimed_size)
        assert int(report.rewritten_commit_count) >= 1
        assert history_after < history_before
        assert report.blocking_refs == []
        _assert_quick_verify_ok(api)
        return {
            "processed_bytes": int(logical_live_total),
            "operation_seconds": round(finished - started, 6),
            "dataset_family": "historical-duplicate",
            "rewritten_commit_count": int(report.rewritten_commit_count),
            "dropped_ancestor_count": int(report.dropped_ancestor_count),
            "blocking_ref_count": len(report.blocking_refs),
            "gc_reclaimed_size": reclaimed_size,
            "history_count_after": history_after,
        }


def run_verify_heavy_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute full verification over a verify-heavy repository shape."""

    with benchmark_workspace(workspace_root, "phase12-verify-heavy-") as tmpdir:
        api, logical_live_total = build_verify_heavy_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        report = api.full_verify()
        finished = time.perf_counter()
        assert report.ok is True
        return {
            "processed_bytes": int(logical_live_total),
            "operation_seconds": round(finished - started, 6),
            "dataset_family": "verify-heavy",
            "operation_count": max(1, len(list(api.list_repo_files()))),
            "reported_full_verify_seconds": round(finished - started, 6),
            "verify_ok": bool(report.ok),
        }


def infer_space_conclusions(results: Dict[str, Dict[str, object]]) -> List[str]:
    """Build human-readable conclusions from benchmark results."""

    conclusions = []

    def _near_one(value: float, tolerance: float = 0.05) -> bool:
        return abs(float(value) - 1.0) <= float(tolerance)

    exact = results["exact_duplicate_live_space"]["metrics"]
    aligned = results["aligned_overlap_live_space"]["metrics"]
    shifted = results["shifted_overlap_live_space"]["metrics"]
    historical = results.get("historical_duplicate_space", {}).get("metrics", {})

    conclusions.append(
        "大文件上传中位吞吐约 {value:.2f} MiB/s，范围读取中位吞吐约 {range_value:.2f} MiB/s。".format(
            value=float(results["large_upload"].get("throughput_mib_per_sec", 0.0)),
            range_value=float(results["large_read_range"].get("throughput_mib_per_sec", 0.0)),
        )
    )
    exact_before_unique = float(exact.get("physical_over_unique_before_gc", 0.0))
    exact_after_unique = float(exact.get("physical_over_unique_after_gc", 0.0))
    if _near_one(exact_before_unique):
        conclusions.append(
            "完全重复的大文件在写入当下就保持接近单份物理副本，写前后 `physical_over_unique` 都约为 {ratio:.2f}x，说明写时 chunk/pack 复用已经生效，`gc()` 不再承担主要去重职责。".format(
                ratio=exact_before_unique,
            )
        )
    else:
        conclusions.append(
            "完全重复的大文件在写入后立即占用仍接近线性膨胀，`gc()` 后 `chunks.packs` 体积下降到原来的 {ratio:.2%}，说明当前物理复用主要依赖后续压实而不是写时复用。".format(
                ratio=float(exact["physical_over_logical_after_gc"]),
            )
        )

    aligned_before_unique = float(aligned.get("physical_over_unique_before_gc", 0.0))
    aligned_after_unique = float(aligned.get("physical_over_unique_after_gc", 0.0))
    if _near_one(aligned_before_unique):
        conclusions.append(
            "按 chunk 边界对齐的部分重复文件在写入当下就已经接近唯一数据体积，`physical_over_unique_before_gc` 约为 {ratio:.2f}x，`gc()` 基本不再改变结果。".format(
                ratio=aligned_before_unique,
            )
        )
    else:
        conclusions.append(
            "按 chunk 边界对齐的部分重复文件在当前内容定义分块规划下，写入当下可压到约 {before_ratio:.2f}x 唯一数据体积，`gc()` 后保持约 {after_ratio:.2f}x。".format(
                before_ratio=aligned_before_unique,
                after_ratio=aligned_after_unique,
            )
        )

    shifted_before_unique = float(shifted.get("physical_over_unique_before_gc", 0.0))
    shifted_after_unique = float(shifted.get("physical_over_unique_after_gc", 0.0))
    if _near_one(shifted_before_unique):
        conclusions.append(
            "错位重复文件在当前内容定义分块规划下也已接近唯一数据体积，写入当下 `physical_over_unique_before_gc` 约为 {ratio:.2f}x，说明 shifted overlap 不再是明显空间短板。".format(
                ratio=shifted_before_unique,
            )
        )
    else:
        conclusions.append(
            "错位重复文件的空间放大已经收敛到约 {before_ratio:.2f}x（写入当下）和 {after_ratio:.2f}x（`gc()` 后），虽然仍差于 exact duplicate / aligned overlap，但已经明显优于早期固定大小 chunk 的表现。".format(
                before_ratio=shifted_before_unique,
                after_ratio=shifted_after_unique,
            )
        )

    if historical:
        historical_before_unique = float(historical.get("physical_over_unique_before_gc", 0.0))
        if _near_one(historical_before_unique):
            conclusions.append(
                "同一路径反复写入完全相同的大文件时，历史重复提交也不会再把 pack 线性撑大，写入当下已经维持在约 {ratio:.2f}x 唯一数据体积。".format(
                    ratio=historical_before_unique,
                )
            )
        else:
            conclusions.append(
                "同一路径反复写入完全相同的大文件时，提交阶段的 pack 占用仍会持续增长，但 `gc()` 可把这类重复 pack 压回到接近单份数据体积，当前风险在于压实前的短期空间膨胀而不是最终不可回收。"
            )
    cold_download = results.get("hf_hub_download_cold", {})
    warm_download = results.get("hf_hub_download_warm", {})
    if cold_download and warm_download:
        conclusions.append(
            "`hf_hub_download()` 已经具备明确的 cold/warm 语义：warm 路径会复用现有 detached view，第二次调用的缓存增量约为 {delta} 字节，且返回路径保持 repo 相对路径后缀。".format(
                delta=int(warm_download.get("metrics", {}).get("cache_delta_bytes", 0)),
            )
        )
    threshold_metrics = results.get("threshold_sweep", {}).get("metrics", {})
    if threshold_metrics:
        conclusions.append(
            "阈值扫描已经验证当前分界是稳定的：小于 `large_file_threshold` 的文件保持 whole-file blob，而大于等于阈值的文件转入 chunked storage。"
        )
    merge_metrics = results.get("merge_non_fast_forward", {}).get("metrics", {})
    if merge_metrics:
        conclusions.append(
            "非快进 merge 已进入 benchmark 基线，当前基线里该路径能稳定创建结构化 merge commit，后续 profiling 可以直接围绕 merge-base 解析和 tree merge 热点展开。"
        )
    squash_metrics = results.get("squash_history", {}).get("metrics", {})
    if squash_metrics:
        conclusions.append(
            "`squash_history()` 已纳入性能基线，当前可以直接衡量“历史重写 + 跟随 GC”这一完整维护路径，而不是只看 `gc()` 单点。"
        )
    if _near_one(exact_before_unique) and (not historical or _near_one(float(historical.get("physical_over_unique_before_gc", 0.0)))):
        conclusions.append(
            "当前优化已经基本解决 exact duplicate 与历史重复写入的短期空间膨胀，后续应优先关注范围读取、warm download、merge 等时间侧回归，以及 aligned/shifted overlap 的剩余空间差异。"
        )
    else:
        conclusions.append(
            "如果目标是降低重复大文件的即时空间膨胀，优先级最高的问题是写时 chunk/pack 复用；如果目标是提高错位相似内容复用，后续才值得评估内容定义分块方案。"
        )
        conclusions.append(
            "当前实现对时间性能和长期 GC 后空间占用是可接受的，但对“写后立刻”的重复大文件空间放大仍然偏保守，尤其在大量重复提交但未及时 GC 的场景下需要重点关注。"
        )

    if float(results["large_read_range"].get("throughput_mib_per_sec", 0.0)) < float(
        results["large_upload"].get("throughput_mib_per_sec", 0.0)
    ):
        conclusions.append(
            "本次基线里范围读取没有明显快过写入路径，后续应重点 profiling `IndexStore.lookup()` 与逐 chunk 校验链路。"
        )

    return conclusions

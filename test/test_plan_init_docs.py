import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
_PLAN_INIT_DIR = _REPO_ROOT / "plan" / "init"
_PLAN_README = _PLAN_INIT_DIR / "README.md"
_AGENTS_FILE = _REPO_ROOT / "AGENTS.md"
_EXPECTED_PLAN_DOCS = [
    "00-scope.md",
    "01-architecture.md",
    "02-storage-format.md",
    "03-transaction-consistency.md",
    "04-api-compat.md",
    "05-gc-roadmap.md",
    "06-phase-execution.md",
]
_DOC_MARKERS = {
    "00-scope.md": ["当前仓库基线", "MVP 切分", "成功标准"],
    "01-architecture.md": ["推荐包结构", "MVP 简化架构", "HubVaultApi"],
    "02-storage-format.md": ["Phase 1 MVP 布局", "Blob 对象", "路径规范化"],
    "03-transaction-consistency.md": ["事务状态机", "线性化点", "quick_verify()"],
    "04-api-compat.md": ["HubVaultApi", "CommitOperationAdd", "VerifyReport"],
    "05-gc-roadmap.md": ["GC Root 定义", "quick_verify()", "测试路线图"],
    "06-phase-execution.md": ["Phase 0", "Phase 1. MVP 仓库核心", "Checklist"],
}
_DOCS_WITH_PYTHON_SNIPPETS = [
    "00-scope.md",
    "01-architecture.md",
    "02-storage-format.md",
    "03-transaction-consistency.md",
    "04-api-compat.md",
    "05-gc-roadmap.md",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.unittest
class TestPlanInitDocs:
    def test_init_readme_lists_all_expected_documents(self):
        text = _read_text(_PLAN_README)

        for filename in _EXPECTED_PLAN_DOCS:
            assert filename in text

    def test_each_plan_document_contains_required_markers(self):
        for filename, markers in _DOC_MARKERS.items():
            text = _read_text(_PLAN_INIT_DIR / filename)
            for marker in markers:
                assert marker in text

    def test_technical_documents_include_python_snippets(self):
        for filename in _DOCS_WITH_PYTHON_SNIPPETS:
            text = _read_text(_PLAN_INIT_DIR / filename)
            assert "```python" in text

    def test_phase_execution_uses_checkbox_todos_and_checklists(self):
        text = _read_text(_PLAN_INIT_DIR / "06-phase-execution.md")
        phase_sections = list(
            re.finditer(r"^## (Phase [^\n]+)\n(?P<body>.*?)(?=^## Phase |\Z)", text, flags=re.MULTILINE | re.DOTALL)
        )

        assert phase_sections

        for match in phase_sections:
            body = match.group("body")
            assert "### Todo" in body
            assert "### Checklist" in body

            todo_text = body.split("### Todo", 1)[1].split("### Checklist", 1)[0]
            checklist_text = body.split("### Checklist", 1)[1]

            assert re.search(r"^\* \[ \] ", todo_text, flags=re.MULTILINE)
            assert re.search(r"^\* \[ \] ", checklist_text, flags=re.MULTILINE)

    def test_agents_capture_public_testing_and_regression_rules(self):
        text = _read_text(_AGENTS_FILE).lower()

        for marker in [
            "public",
            "private",
            "protected",
            "mock",
            "plan/",
            "make unittest",
            "regression",
        ]:
            assert marker in text

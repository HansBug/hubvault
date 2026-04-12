"""Launch a real hubvault frontend server for Playwright checks."""

import tempfile
from pathlib import Path

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.optional import import_optional_dependency
from hubvault.server import ServerConfig, create_app


HOST = "127.0.0.1"
PORT = 9613

SVG_V1 = b"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<rect width="640" height="360" fill="#ecfeff"/>
<rect y="228" width="640" height="132" fill="#bae6fd"/>
<circle cx="528" cy="84" r="40" fill="#67e8f9"/>
<path d="M0 244L110 150L240 244Z" fill="#0f766e"/>
<path d="M170 244L322 106L536 244Z" fill="#14b8a6"/>
<path d="M414 244L514 166L640 244Z" fill="#0d9488"/>
<rect x="116" y="76" width="408" height="174" rx="30" fill="#ffffff"/>
<rect x="144" y="104" width="108" height="108" rx="28" fill="#115e59"/>
<path d="M176 160H216V138L246 160L216 182V160H176Z" fill="#ccfbf1"/>
<circle cx="192" cy="132" r="8" fill="#5eead4"/>
<circle cx="224" cy="132" r="8" fill="#99f6e4"/>
<text x="278" y="124" font-family="Verdana, Geneva, sans-serif" font-size="28" font-weight="700" fill="#0f766e">HubVault</text>
<text x="278" y="152" font-family="Verdana, Geneva, sans-serif" font-size="14" fill="#155e75">Portable repository snapshots</text>
<rect x="278" y="176" width="194" height="14" rx="7" fill="#0f766e"/>
<rect x="278" y="202" width="164" height="12" rx="6" fill="#67e8f9"/>
<rect x="486" y="170" width="18" height="18" rx="9" fill="#14b8a6"/>
<rect x="510" y="170" width="18" height="18" rx="9" fill="#5eead4"/>
<rect x="92" y="272" width="132" height="48" rx="16" fill="#115e59"/>
<rect x="244" y="280" width="146" height="40" rx="14" fill="#14b8a6"/>
<rect x="410" y="270" width="138" height="50" rx="16" fill="#0f766e"/>
<rect x="112" y="286" width="22" height="22" rx="6" fill="#ccfbf1"/>
<rect x="144" y="286" width="56" height="10" rx="5" fill="#99f6e4"/>
<rect x="144" y="302" width="42" height="8" rx="4" fill="#5eead4"/>
<rect x="270" y="292" width="94" height="8" rx="4" fill="#ccfbf1"/>
<rect x="434" y="286" width="26" height="26" rx="8" fill="#99f6e4"/>
<rect x="470" y="286" width="54" height="10" rx="5" fill="#ccfbf1"/>
<rect x="470" y="302" width="42" height="8" rx="4" fill="#5eead4"/>
</svg>
"""

SVG_V2 = b"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<rect width="640" height="360" fill="#dff7fb"/>
<rect y="220" width="640" height="140" fill="#99f6e4"/>
<circle cx="500" cy="76" r="46" fill="#2dd4bf"/>
<path d="M0 236L118 156L258 236Z" fill="#115e59"/>
<path d="M194 236L350 96L560 236Z" fill="#0f766e"/>
<path d="M430 236L520 168L640 236Z" fill="#14b8a6"/>
<rect x="108" y="70" width="424" height="184" rx="32" fill="#f8fafc"/>
<rect x="136" y="96" width="116" height="116" rx="30" fill="#0f766e"/>
<path d="M174 126H214L232 160L214 194H174L156 160Z" fill="#ccfbf1"/>
<circle cx="194" cy="160" r="10" fill="#14b8a6"/>
<text x="278" y="122" font-family="Verdana, Geneva, sans-serif" font-size="28" font-weight="700" fill="#0f766e">HubVault Sync</text>
<text x="278" y="150" font-family="Verdana, Geneva, sans-serif" font-size="14" fill="#155e75">Dedup chunks, inspect diffs, restore fast</text>
<rect x="278" y="174" width="176" height="14" rx="7" fill="#0f766e"/>
<rect x="278" y="198" width="216" height="12" rx="6" fill="#2dd4bf"/>
<rect x="278" y="220" width="150" height="12" rx="6" fill="#67e8f9"/>
<rect x="462" y="110" width="54" height="26" rx="13" fill="#14b8a6"/>
<text x="479" y="128" font-family="Verdana, Geneva, sans-serif" font-size="13" font-weight="700" fill="#ecfeff">v2</text>
<rect x="84" y="272" width="148" height="52" rx="18" fill="#0f766e"/>
<rect x="246" y="280" width="154" height="44" rx="16" fill="#14b8a6"/>
<rect x="414" y="266" width="154" height="58" rx="18" fill="#115e59"/>
<circle cx="126" cy="298" r="14" fill="#ccfbf1"/>
<rect x="148" y="290" width="60" height="10" rx="5" fill="#99f6e4"/>
<rect x="148" y="306" width="44" height="8" rx="4" fill="#5eead4"/>
<rect x="272" y="292" width="100" height="8" rx="4" fill="#ccfbf1"/>
<rect x="272" y="306" width="82" height="8" rx="4" fill="#99f6e4"/>
<rect x="438" y="284" width="30" height="30" rx="10" fill="#99f6e4"/>
<rect x="478" y="286" width="60" height="10" rx="5" fill="#ccfbf1"/>
<rect x="478" y="302" width="48" height="8" rx="4" fill="#5eead4"/>
</svg>
"""


def _build_fixture_repo(repo_dir: Path) -> None:
    api = HubVaultApi(repo_dir, revision="release/v1")
    api.create_repo(default_branch="release/v1")

    first_commit = api.create_commit(
        operations=[
            CommitOperationAdd(
                "README.md",
                (
                    b"# HubVault Fixture\n\n"
                    b"This repository exists for the Phase 9 frontend smoke tests.\n\n"
                    b"- README rendering\n"
                    b"- standalone file pages\n"
                    b"- commit diff pages\n"
                    b"- upload queues\n"
                    b"- image preview and compare\n"
                ),
            ),
            CommitOperationAdd("docs/guide.md", b"# Guide\n\nVersion 1 guide.\n"),
            CommitOperationAdd("configs/config.json", b"{\"version\": 1}\n"),
            CommitOperationAdd("src/app.py", b"def render_message():\n    return 'fixture v1'\n"),
            CommitOperationAdd("images/logo.svg", SVG_V1),
            CommitOperationAdd("artifacts/model.bin", b"fixture-model-v1\n"),
        ],
        commit_message="seed frontend fixture",
    )
    api.create_branch(branch="dev", revision=first_commit.oid)
    api.create_tag(tag="v1.0", revision=first_commit.oid)
    api.create_commit(
        operations=[
            CommitOperationAdd("docs/guide.md", b"# Guide\n\nVersion 2 guide.\n"),
            CommitOperationAdd("docs/changelog.md", b"# Changelog\n\n- Added phase9 fixture coverage.\n"),
            CommitOperationAdd("src/app.py", b"def render_message():\n    return 'fixture v2'\n"),
            CommitOperationAdd("images/logo.svg", SVG_V2),
            CommitOperationAdd("artifacts/model.bin", b"fixture-model-v2\n"),
        ],
        commit_message="update guide model and ui assets",
    )
    api.hf_hub_download("artifacts/model.bin")


def main() -> int:
    uvicorn = import_optional_dependency(
        "uvicorn",
        extra="api",
        feature="webui e2e fixture server",
        missing_names={"click", "h11", "httptools"},
    )

    with tempfile.TemporaryDirectory(prefix="hubvault-webui-e2e-") as tmpdir:
        repo_dir = Path(tmpdir) / "repo"
        _build_fixture_repo(repo_dir)
        config = ServerConfig(
            repo_path=repo_dir,
            mode="frontend",
            host=HOST,
            port=PORT,
            token_ro=("ro-token",),
            token_rw=("rw-token",),
        )
        uvicorn.run(create_app(config), host=HOST, port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

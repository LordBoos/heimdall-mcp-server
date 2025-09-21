"""Tests for Codex MCP configuration helpers."""

from __future__ import annotations

from pathlib import Path

from heimdall.cli_commands import mcp_commands


def _load_config(path: Path) -> dict:
    """Helper to load TOML using the module's private reader."""

    return mcp_commands._load_toml_config(path)


def test_install_codex_creates_project_local_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    mcp_commands.install_mcp("codex")

    config_path = mcp_commands.get_codex_config_path()
    assert config_path.exists()

    config = _load_config(config_path)
    server_name = mcp_commands.get_server_config().name

    servers = config.get("mcp_servers", {})
    assert server_name in servers
    server_entry = servers[server_name]
    assert server_entry["command"] == "heimdall-mcp"
    assert server_entry["env"]["PROJECT_PATH"] == str(tmp_path)

    status = mcp_commands.check_installation_status(
        "codex", mcp_commands.PLATFORMS["codex"]
    )
    assert status == "✅ Installed"


def test_install_codex_preserves_existing_servers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config_path = mcp_commands.get_codex_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
[mcp_servers.other]
command = "python"
args = [ "-m", "other" ]
env = { PROJECT_PATH = "/tmp/example" }
""".strip()
        + "\n"
    )

    mcp_commands.install_mcp("codex", force=True)

    config = _load_config(config_path)
    servers = config.get("mcp_servers", {})

    assert "other" in servers
    assert mcp_commands.get_server_config().name in servers

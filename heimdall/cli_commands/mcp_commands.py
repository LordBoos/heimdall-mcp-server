"""MCP integration management commands for IDE platforms."""

import json
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from cognitive_memory.core.config import get_project_id

console = Console()


@dataclass
class PlatformConfig:
    """Configuration for MCP platform integration."""

    name: str
    config_file: str  # Project-local config file path
    server_key: str  # "servers" or "mcpServers"
    method: str  # "json_modify" or "cli_command"
    detection_folders: list[str]  # For auto-detection


@dataclass
class ServerConfig:
    """Server configuration template for MCP integration."""

    name: str = "heimdall-cognitive-memory"
    type: str = "stdio"
    command: str = ""  # Will be dynamically set
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


# Platform registry with configuration for each supported IDE
PLATFORMS = {
    "vscode": PlatformConfig(
        name="Visual Studio Code",
        config_file=".vscode/mcp.json",
        server_key="servers",
        method="json_modify",
        detection_folders=[".vscode"],
    ),
    "cursor": PlatformConfig(
        name="Cursor",
        config_file=".vscode/mcp.json",  # Cursor shares VS Code config
        server_key="servers",
        method="json_modify",
        detection_folders=[".cursor"],
    ),
    "visual-studio": PlatformConfig(
        name="Visual Studio",
        config_file=".mcp.json",
        server_key="mcpServers",
        method="json_modify",
        detection_folders=[".vs"],
    ),
    "claude-code": PlatformConfig(
        name="Claude Code",
        config_file="",
        server_key="",
        method="cli_command",
        detection_folders=[],
    ),
    "gemini": PlatformConfig(
        name="Gemini CLI",
        config_file=".gemini/settings.json",
        server_key="mcpServers",
        method="json_modify",
        detection_folders=[],  # Detect via CLI only, not folder
    ),
    "codex": PlatformConfig(
        name="Codex CLI",
        config_file=".heimdall/codex/config.toml",
        server_key="mcp_servers",
        method="toml_project",
        detection_folders=[],
    ),
}


def get_codex_config_path() -> Path:
    """Return project-local Codex config path."""

    project_root = Path.cwd()
    # Codex resolves MCP servers via CODEX_HOME/config.toml. We intentionally
    # keep our config inside the repo so each project can opt-in without
    # polluting the user's global ~/.codex directory.
    return project_root / ".heimdall" / "codex" / "config.toml"


def _load_toml_config(config_path: Path) -> dict[str, Any]:
    """Load TOML configuration, returning an empty dict when missing/invalid."""

    if not config_path.exists():
        return {}

    try:
        return tomllib.loads(config_path.read_text())
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def _format_toml_value(value: Any) -> str:
    """Format Python values into TOML-compatible strings."""

    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        inner = ", ".join(_format_toml_value(item) for item in value)
        return f"[ {inner} ]" if inner else "[]"
    if isinstance(value, dict):
        items = ", ".join(
            f"{key} = {_format_toml_value(val)}" for key, val in sorted(value.items())
        )
        return f"{{ {items} }}" if items else "{}"

    raise TypeError(f"Unsupported TOML value type: {type(value)!r}")


def _serialize_codex_config(config: dict[str, Any]) -> str:
    """Serialize config dict into TOML with stable ordering."""

    lines: list[str] = []

    # Emit non-table values first (not currently used but keeps function generic)
    for key in sorted(k for k in config.keys() if k != "mcp_servers"):
        value = _format_toml_value(config[key])
        lines.append(f"{key} = {value}")

    if "mcp_servers" in config:
        if lines:
            lines.append("")
        servers = config["mcp_servers"]
        if isinstance(servers, dict):
            for server_name in sorted(servers.keys()):
                server_data = servers[server_name]
                lines.append(f"[mcp_servers.{server_name}]")
                if isinstance(server_data, dict):
                    for field in ("command", "args", "env", "startup_timeout_ms"):
                        if field in server_data:
                            value = _format_toml_value(server_data[field])
                            lines.append(f"{field} = {value}")
                lines.append("")

    content = "\n".join(lines).rstrip()
    return f"{content}\n" if content else ""


def _write_codex_config(config_path: Path, config: dict[str, Any]) -> None:
    """Write TOML config to disk, ensuring parent directory exists."""

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_serialize_codex_config(config))


def _ensure_codex_config(server_config: ServerConfig, force: bool = False) -> None:
    """Insert or update the Codex MCP server entry."""

    config_path = get_codex_config_path()
    config = _load_toml_config(config_path)

    current_servers = config.setdefault("mcp_servers", {})
    if not isinstance(current_servers, dict):
        current_servers = {}
        config["mcp_servers"] = current_servers

    desired_entry = {
        "command": server_config.command,
        "args": server_config.args,
        "env": server_config.env,
    }

    existing_entry = current_servers.get(server_config.name)

    if existing_entry and not force:
        existing_command = existing_entry.get("command")
        existing_env = existing_entry.get("env", {}) if isinstance(existing_entry, dict) else {}
        project_env = server_config.env.get("PROJECT_PATH", "")
        env_matches = isinstance(existing_env, dict) and existing_env.get("PROJECT_PATH") == project_env

        if existing_command != server_config.command or not env_matches:
            console.print(
                "⚠️  Codex config already contains this server with different settings"
            )
            console.print("   Current command: " + str(existing_command))
            console.print(f"   Expected command: {server_config.command}")
            console.print("   Use --force to overwrite the entry")
            return

    current_servers[server_config.name] = desired_entry
    _write_codex_config(config_path, config)

    console.print(f"✅ Codex MCP config written to: {config_path}")
    console.print("   Launch Codex with this project config via:")
    console.print(
        f"   CODEX_HOME={config_path.parent} codex"
    )


def _render_codex_snippet(server_config: ServerConfig) -> str:
    """Create TOML snippet for manual configuration."""

    snippet = {
        "mcp_servers": {
            server_config.name: {
                "command": server_config.command,
                "args": server_config.args,
                "env": server_config.env,
            }
        }
    }
    return _serialize_codex_config(snippet)


def get_server_config() -> ServerConfig:
    """Generate server config with current project paths."""
    project_root = Path.cwd()
    project_id = get_project_id(project_root)  # Use the proper project ID function

    return ServerConfig(
        name=f"heimdall-{project_id}",
        command="heimdall-mcp",  # Use the installed entry point
        env={"PROJECT_PATH": str(project_root)},
    )


def detect_platforms() -> list[str]:
    """Detect available platforms in current directory."""
    detected = []
    current_dir = Path.cwd()

    # Command mapping for CLI-based platforms
    cli_commands = {
        "claude-code": "claude",
        "gemini": "gemini",
        "cursor": "cursor",
        "vscode": "code",
        "codex": "codex",
    }

    for platform_id, config in PLATFORMS.items():
        # Check CLI availability for platforms that have CLI commands
        if platform_id in cli_commands:
            try:
                result = subprocess.run(
                    [cli_commands[platform_id], "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    detected.append(platform_id)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Also check for detection folders (for project-specific detection)
        for folder in config.detection_folders:
            if (current_dir / folder).exists():
                if platform_id not in detected:
                    detected.append(platform_id)
                break

        # Detect based on project-local config files
        if config.config_file:
            if (current_dir / config.config_file).exists() and platform_id not in detected:
                detected.append(platform_id)

    return detected


def find_config_file(platform_config: PlatformConfig) -> Path | None:
    """Find existing config file or return preferred location."""
    if not platform_config.config_file:
        return None

    config_path = Path.cwd() / platform_config.config_file
    return config_path


def check_installation_status(platform_id: str, platform_config: PlatformConfig) -> str:
    """Check if heimdall MCP server is already configured for the platform."""
    server_config = get_server_config()

    if platform_config.method == "cli_command":
        # Check Claude Code via CLI
        try:
            result = subprocess.run(
                ["claude", "mcp", "list"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                # Check if our server is in the output
                if server_config.name in result.stdout:
                    return "✅ Installed"
                else:
                    return "❌ Not configured"
            else:
                return "⚠️ CLI error"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "❌ Claude CLI unavailable"

    elif platform_config.method == "toml_project":
        config_path = find_config_file(platform_config)
        if not config_path or not config_path.exists():
            return "❌ Not configured"

        config = _load_toml_config(config_path)
        servers = config.get("mcp_servers")
        if not isinstance(servers, dict):
            return "⚠️ Invalid config"

        server_entry = servers.get(server_config.name)
        if not isinstance(server_entry, dict):
            return "❌ Not configured"

        command_matches = server_entry.get("command") == server_config.command
        env = server_entry.get("env")
        env_path = ""
        if isinstance(env, dict):
            env_path = str(env.get("PROJECT_PATH", ""))
        expected_path = server_config.env.get("PROJECT_PATH", "")

        if command_matches and env_path == expected_path:
            return "✅ Installed"
        return "⚠️ Outdated path"

    else:
        # Check JSON-based platforms
        config_path = find_config_file(platform_config)
        if not config_path or not config_path.exists():
            return "❌ Not configured"

        try:
            with open(config_path) as f:
                config = json.load(f)

            # Check if server section exists and contains our server
            if (
                platform_config.server_key in config
                and server_config.name in config[platform_config.server_key]
            ):
                server_entry = config[platform_config.server_key][server_config.name]

                # Check if command path matches current project
                if server_entry.get("command") == server_config.command:
                    return "✅ Installed"
                else:
                    return "⚠️ Outdated path"
            else:
                return "❌ Not configured"

        except (json.JSONDecodeError, KeyError):
            return "⚠️ Invalid config"


def modify_json_config(
    config_path: Path,
    server_config: ServerConfig,
    platform_config: PlatformConfig,
    force: bool = False,
) -> None:
    """Safely modify JSON config, preserving existing servers."""
    try:
        # Create parent directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing config or create new structure
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
        else:
            config = {}

        # Ensure server section exists
        if platform_config.server_key not in config:
            config[platform_config.server_key] = {}

        # Check if server already exists
        server_exists = server_config.name in config[platform_config.server_key]
        if server_exists and not force:
            existing_command = config[platform_config.server_key][
                server_config.name
            ].get("command", "")
            if existing_command != server_config.command:
                console.print(
                    f"⚠️  Server '{server_config.name}' already exists with different path:"
                )
                console.print(f"   Current: {existing_command}")
                console.print(f"   New:     {server_config.command}")
                console.print("   Use --force to overwrite")
                return

        # Add/update server configuration
        config[platform_config.server_key][server_config.name] = {
            "type": server_config.type,
            "command": server_config.command,
            "args": server_config.args,
            "env": server_config.env,
        }

        # Write back with proper formatting
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2, sort_keys=True)

        action = "Updated" if server_exists else "Added"
        console.print(f"✅ {action} MCP server configuration in: {config_path}")

    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in config file: {e}") from e
    except PermissionError as e:
        raise Exception(f"Permission denied writing to: {config_path}") from e
    except Exception as e:
        raise Exception(f"Failed to modify config: {e}") from e


def execute_claude_mcp_add(server_config: ServerConfig, force: bool = False) -> None:
    """Execute 'claude mcp add' command."""
    try:
        # Check if claude CLI is available
        try:
            subprocess.run(
                ["claude", "--version"], capture_output=True, check=True, timeout=5
            )
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ) as e:
            raise Exception(
                "Claude CLI not found. Please install Claude Code first."
            ) from e

        # Check if server already exists (unless force)
        if not force:
            try:
                result = subprocess.run(
                    ["claude", "mcp", "list"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and server_config.name in result.stdout:
                    console.print(
                        f"⚠️  Server '{server_config.name}' already exists in Claude Code"
                    )
                    console.print("   Use --force to overwrite")
                    return
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                # Continue if list command fails
                pass

        # Build the command array
        cmd = ["claude", "mcp", "add", server_config.name, "--scope", "project"]

        # Add environment variables
        for key, value in server_config.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add transport and command (no separator needed for entry point)
        cmd.extend(["--transport", "stdio", server_config.command])

        # Add arguments if any
        if server_config.args:
            cmd.extend(server_config.args)

        console.print("🔧 Executing Claude MCP add command...")
        console.print(f"   Command: {' '.join(cmd)}")

        # Execute the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            console.print(
                "✅ Successfully added MCP server to Claude Code (project scope)"
            )
            if result.stdout.strip():
                console.print(f"   Output: {result.stdout.strip()}")
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            if "already exists" in error_msg.lower() and not force:
                console.print("⚠️  Server already exists. Use --force to overwrite")
            else:
                raise Exception(f"Claude MCP add failed: {error_msg}")

    except subprocess.TimeoutExpired as e:
        raise Exception("Claude MCP command timed out") from e
    except Exception as e:
        raise Exception(f"Failed to execute Claude MCP add: {e}") from e


def generate_config_snippet(
    platform_config: PlatformConfig, server_config: ServerConfig
) -> dict:
    """Generate config snippet for manual addition."""
    return {
        platform_config.server_key: {
            server_config.name: {
                "type": server_config.type,
                "command": server_config.command,
                "args": server_config.args,
                "env": server_config.env,
            }
        }
    }


def install_mcp(
    platform: str = typer.Argument(
        ..., help="Platform: vscode, cursor, visual-studio, claude-code, gemini"
    ),
    force: bool = typer.Option(False, help="Overwrite existing configuration"),
) -> None:
    """Install MCP server configuration for specified platform."""
    try:
        if platform not in PLATFORMS:
            console.print(f"❌ Unknown platform: {platform}", style="bold red")
            console.print(f"Available platforms: {', '.join(PLATFORMS.keys())}")
            raise typer.Exit(1)

        platform_config = PLATFORMS[platform]
        server_config = get_server_config()

        console.print(f"🔗 Installing MCP server for {platform_config.name}")

        if platform_config.method == "json_modify":
            config_path = find_config_file(platform_config)
            if config_path:
                modify_json_config(config_path, server_config, platform_config, force)

                # Verify installation
                status = check_installation_status(platform, platform_config)
                if status == "✅ Installed":
                    console.print(
                        f"🎉 MCP installation completed for {platform_config.name}"
                    )
                else:
                    console.print(
                        f"⚠️  Installation may not be complete. Status: {status}"
                    )
            else:
                console.print(
                    f"❌ Could not determine config file location for {platform}"
                )
                raise typer.Exit(1)

        elif platform_config.method == "toml_project":
            _ensure_codex_config(server_config, force)

            status = check_installation_status(platform, platform_config)
            if status == "✅ Installed":
                console.print(
                    f"🎉 Codex configuration ready for {platform_config.name}"
                )
            else:
                console.print(f"⚠️  Installation status: {status}")

        elif platform_config.method == "cli_command":
            execute_claude_mcp_add(server_config, force)

            # Verify installation
            status = check_installation_status(platform, platform_config)
            if status == "✅ Installed":
                console.print(
                    f"🎉 MCP installation completed for {platform_config.name}"
                )
            else:
                console.print(f"⚠️  Installation may not be complete. Status: {status}")

        # Show next steps
        console.print("\n💡 Next steps:")
        if platform == "claude-code":
            console.print("   • Restart Claude Code to load the new MCP server")
            console.print("   • Test with: claude tools list")
        elif platform == "codex":
            codex_config_home = get_codex_config_path().parent
            console.print(
                "   • Launch Codex with project-local config:"
            )
            console.print(f"     CODEX_HOME={codex_config_home} codex")
            console.print("   • Optional: add --config-home PATH to your Codex alias")
        else:
            console.print(
                f"   • Restart {platform_config.name} to load the new MCP server"
            )
            console.print("   • Check that the tools are available in the IDE")

    except Exception as e:
        console.print(f"❌ Error installing MCP for {platform}: {e}", style="bold red")
        raise typer.Exit(1) from e


def list_mcp() -> None:
    """List available platforms and installation status."""
    try:
        console.print("🔗 MCP Platform Overview", style="bold blue")

        table = Table(title="Supported Platforms")
        table.add_column("Platform", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Config File", style="yellow")
        table.add_column("Method", style="green")
        table.add_column("Status", style="white")

        detected_platforms = detect_platforms()

        for platform_id, config in PLATFORMS.items():
            status = (
                "✅ Detected" if platform_id in detected_platforms else "❌ Not found"
            )
            config_file = config.config_file if config.config_file else "CLI managed"

            table.add_row(platform_id, config.name, config_file, config.method, status)

        console.print(table)

        if detected_platforms:
            console.print(f"\n📍 Detected platforms: {', '.join(detected_platforms)}")
        else:
            console.print("\n⚠️  No platforms detected in current directory")

    except Exception as e:
        console.print(f"❌ Error listing platforms: {e}", style="bold red")
        raise typer.Exit(1) from e


def remove_mcp(
    platform: str = typer.Argument(..., help="Platform to remove from"),
) -> None:
    """Remove MCP server from specified platform."""
    try:
        if platform not in PLATFORMS:
            console.print(f"❌ Unknown platform: {platform}", style="bold red")
            console.print(f"Available platforms: {', '.join(PLATFORMS.keys())}")
            raise typer.Exit(1)

        platform_config = PLATFORMS[platform]
        server_config = get_server_config()

        console.print(f"🗑️  Removing MCP server from {platform_config.name}")

        if platform_config.method == "cli_command":
            # Remove from Claude Code via CLI
            try:
                subprocess.run(
                    ["claude", "--version"], capture_output=True, check=True, timeout=5
                )
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ) as e:
                console.print("❌ Claude CLI not found. Cannot remove MCP server.")
                raise typer.Exit(1) from e

            try:
                result = subprocess.run(
                    ["claude", "mcp", "remove", server_config.name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    console.print("✅ MCP server removed from Claude Code")
                    if result.stdout.strip():
                        console.print(f"   Output: {result.stdout.strip()}")
                else:
                    error_msg = (
                        result.stderr.strip() if result.stderr else "Unknown error"
                    )
                    if "not found" in error_msg.lower():
                        console.print(
                            f"⚠️  Server '{server_config.name}' was not configured"
                        )
                    else:
                        raise Exception(f"Claude MCP remove failed: {error_msg}")

            except subprocess.TimeoutExpired as e:
                raise Exception("Claude MCP remove command timed out") from e
            except Exception as e:
                raise Exception(f"Failed to execute Claude MCP remove: {e}") from e

        else:
            # Remove from JSON-based platforms
            config_path = find_config_file(platform_config)
            if not config_path or not config_path.exists():
                console.print(f"⚠️  No configuration file found at: {config_path}")
                return

            try:
                with open(config_path) as f:
                    config = json.load(f)

                # Check if server section exists and contains our server
                if (
                    platform_config.server_key in config
                    and server_config.name in config[platform_config.server_key]
                ):
                    # Remove our server
                    del config[platform_config.server_key][server_config.name]

                    # Remove empty server section if it's now empty
                    if not config[platform_config.server_key]:
                        del config[platform_config.server_key]

                    # Write back the updated config
                    with open(config_path, "w") as f:
                        json.dump(config, f, indent=2, sort_keys=True)

                    console.print(f"✅ MCP server removed from {platform_config.name}")
                    console.print(f"   Updated: {config_path}")
                else:
                    console.print(
                        f"⚠️  Server '{server_config.name}' was not configured in {platform_config.name}"
                    )

            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON in config file: {e}") from e
            except PermissionError as e:
                raise Exception(f"Permission denied writing to: {config_path}") from e
            except Exception as e:
                raise Exception(f"Failed to modify config: {e}") from e

    except Exception as e:
        console.print(f"❌ Error removing MCP from {platform}: {e}", style="bold red")
        raise typer.Exit(1) from e


def status_mcp() -> None:
    """Show installation status for all detected platforms."""
    try:
        console.print("📊 MCP Installation Status", style="bold blue")

        detected_platforms = detect_platforms()

        if not detected_platforms:
            console.print("⚠️  No IDE platforms detected in current directory")
            console.print("\n💡 Available platforms:")
            for _platform_id, config in PLATFORMS.items():
                if config.detection_folders:
                    folders = ", ".join(config.detection_folders)
                    console.print(f"   • {config.name}: Create {folders} folder")
                else:
                    console.print(f"   • {config.name}: Install Claude CLI")
            return

        table = Table(title="Installation Status")
        table.add_column("Platform", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Config File", style="yellow")
        table.add_column("Installation Status", style="white")
        table.add_column("Details", style="dim")

        for platform_id in detected_platforms:
            config = PLATFORMS[platform_id]
            config_path = find_config_file(config)

            # Get actual installation status
            status = check_installation_status(platform_id, config)

            # Add helpful details
            if status == "✅ Installed":
                details = "Ready to use"
            elif status == "⚠️ Outdated path":
                details = "Needs update"
            elif status == "❌ Not configured":
                details = "Run 'heimdall mcp install'"
            else:
                details = "Check platform setup"

            table.add_row(
                platform_id,
                config.name,
                str(config_path) if config_path else "CLI managed",
                status,
                details,
            )

        console.print(table)

        # Show summary and next steps
        installed_count = sum(
            1
            for p in detected_platforms
            if check_installation_status(p, PLATFORMS[p]) == "✅ Installed"
        )

        console.print(
            f"\n📈 Summary: {installed_count}/{len(detected_platforms)} platforms configured"
        )

        if installed_count < len(detected_platforms):
            console.print("\n💡 Next steps:")
            console.print("   • Install: heimdall mcp install <platform>")
            console.print("   • Generate config: heimdall mcp generate <platform>")

    except Exception as e:
        console.print(f"❌ Error checking status: {e}", style="bold red")
        raise typer.Exit(1) from e


def generate_mcp(
    platform: str = typer.Argument(..., help="Platform to generate config for"),
    output: str | None = typer.Option(None, help="Output file path"),
) -> None:
    """Generate configuration snippets for manual installation."""
    try:
        if platform not in PLATFORMS:
            console.print(f"❌ Unknown platform: {platform}", style="bold red")
            console.print(f"Available platforms: {', '.join(PLATFORMS.keys())}")
            raise typer.Exit(1)

        platform_config = PLATFORMS[platform]
        server_config = get_server_config()

        console.print(f"📝 Generating MCP configuration for {platform_config.name}")

        if platform_config.method == "cli_command":
            # Generate CLI command for Claude Code
            cmd_parts = [
                "claude",
                "mcp",
                "add",
                server_config.name,
                "--scope",
                "project",
            ]

            # Add environment variables
            for key, value in server_config.env.items():
                cmd_parts.extend(["-e", f"{key}={value}"])

            # Add transport and command
            cmd_parts.extend(["--transport", "stdio", server_config.command])
            if server_config.args:
                cmd_parts.extend(server_config.args)

            command = " ".join(cmd_parts)

            # Display with syntax highlighting
            console.print("\n[bold green]Command to run:[/bold green]")
            syntax = Syntax(command, "bash", theme="monokai", line_numbers=False)
            console.print(syntax)

            # Show usage instructions
            console.print("\n[bold blue]Instructions:[/bold blue]")
            console.print("• Run this command from your project directory")
            console.print(
                "• This will configure Claude Code for project-local MCP access"
            )
            console.print(
                "• Project-local configuration (isolates MCP to current project)"
            )

            if output:
                with open(output, "w") as f:
                    f.write(
                        f"#!/bin/bash\n# MCP configuration for {platform_config.name}\n{command}\n"
                    )
                console.print(f"✅ Command saved to: {output}")

        elif platform_config.method == "toml_project":
            snippet = _render_codex_snippet(server_config)

            console.print(
                f"\n[bold green]Configuration for {platform_config.config_file}:[/bold green]"
            )
            syntax = Syntax(snippet, "toml", theme="monokai", line_numbers=False)
            console.print(syntax)

            console.print("\n[bold blue]Instructions:[/bold blue]")
            console.print(
                "• Create the directory .heimdall/codex if it does not exist"
            )
            console.print(
                f"• Write the snippet above to {platform_config.config_file}"
            )
            console.print(
                "• Start Codex with CODEX_HOME pointing at .heimdall/codex"
            )
            console.print(
                "  (e.g. CODEX_HOME=.heimdall/codex codex --exec)")

            if output:
                output_path = Path(output)
                output_path.write_text(snippet)
                console.print(f"✅ Configuration saved to: {output}")

        else:
            # Generate JSON config for IDE platforms
            config_snippet = generate_config_snippet(platform_config, server_config)
            config_json = json.dumps(config_snippet, indent=2)

            # Display with syntax highlighting
            console.print(
                f"\n[bold green]Configuration for {platform_config.config_file}:[/bold green]"
            )
            syntax = Syntax(config_json, "json", theme="monokai", line_numbers=False)
            console.print(syntax)

            # Show usage instructions
            console.print("\n[bold blue]Instructions:[/bold blue]")
            console.print(f"• Create or edit: {platform_config.config_file}")
            console.print(
                f"• Add the above configuration to the '{platform_config.server_key}' section"
            )
            console.print(
                "• If the file doesn't exist, create it with the full configuration"
            )
            console.print(f"• Restart {platform_config.name} to apply changes")

            if output:
                with open(output, "w") as f:
                    json.dump(config_snippet, f, indent=2)
                console.print(f"✅ Configuration saved to: {output}")

        console.print(f"\n🎉 Configuration generated for {platform_config.name}")

    except Exception as e:
        console.print(f"❌ Error generating config: {e}", style="bold red")
        raise typer.Exit(1) from e


# Helper functions for interactive MCP setup (used by project_init)


def get_mcp_platform_info() -> dict[str, dict]:
    """Get platform detection and installation status information."""
    detected_platforms = detect_platforms()
    platform_info = {}

    for platform_id in detected_platforms:
        config = PLATFORMS[platform_id]
        status = check_installation_status(platform_id, config)

        platform_info[platform_id] = {
            "config": config,
            "status": status,
            "needs_setup": status not in ["✅ Installed"],
        }

    return platform_info


def install_mcp_interactive(platform_id: str, force: bool = False) -> bool:
    """Install MCP for a platform with minimal console output for interactive use."""
    try:
        if platform_id not in PLATFORMS:
            return False

        platform_config = PLATFORMS[platform_id]
        server_config = get_server_config()

        if platform_config.method == "json_modify":
            config_path = find_config_file(platform_config)
            if config_path:
                modify_json_config(config_path, server_config, platform_config, force)
                # Verify installation
                status = check_installation_status(platform_id, platform_config)
                return status == "✅ Installed"
            else:
                return False

        elif platform_config.method == "toml_project":
            _ensure_codex_config(server_config, force)
            status = check_installation_status(platform_id, platform_config)
            return status == "✅ Installed"

        elif platform_config.method == "cli_command":
            execute_claude_mcp_add(server_config, force)
            # Verify installation
            status = check_installation_status(platform_id, platform_config)
            return status == "✅ Installed"

        return False

    except Exception:
        return False


def show_mcp_setup_guide() -> None:
    """Show a brief guide for MCP setup when no platforms are detected."""
    console.print("\n💡 MCP Integration Setup Guide:", style="bold blue")
    console.print(
        "   MCP allows IDE integration with Heimdall's cognitive memory tools."
    )
    console.print("   \n   Supported platforms:")

    for _platform_id, config in PLATFORMS.items():
        if config.detection_folders:
            folders = ", ".join(config.detection_folders)
            console.print(
                f"   • {config.name}: Create {folders} folder in your project"
            )
        else:
            console.print(f"   • {config.name}: Install Claude CLI")

    console.print(
        "   \n   After setting up your IDE, run: heimdall mcp install <platform>"
    )

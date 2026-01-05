#!/usr/bin/env python3
"""
MCP Server for Transcript Saving
Save conversation transcripts to timestamped markdown files for archiving walking journeys.

Tools:
- save_transcript: Save content to a timestamped .md file
- list_transcripts: List saved transcripts
- read_transcript: Read a specific transcript

Organization:
- Transcripts saved to configurable directory (default: ~/transcripts)
- Organized by year/month folders
- Filenames: YYYY-MM-DD_HH-MM-SS_<optional-title>.md
"""

import json
import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)


def get_claude_projects_dir() -> Path:
    """Get the Claude Code projects directory"""
    return Path.home() / ".claude" / "projects"


def cwd_to_project_dir(cwd: str) -> str:
    """Convert a working directory path to Claude's project folder name format.

    Example: C:\\dev -> C--dev
             /home/user/project -> -home-user-project
    """
    # Normalize path separators and convert to Claude's format
    # Replace : with empty, \\ and / with -
    normalized = cwd.replace(":", "").replace("\\", "-").replace("/", "-")
    # Remove leading dash if present
    if normalized.startswith("-"):
        normalized = normalized[1:]
    return normalized


def find_current_session_jsonl(cwd: Optional[str] = None) -> Optional[Path]:
    """Find the most recently modified JSONL file.

    Args:
        cwd: Optional current working directory. If provided, searches that project.
             If not provided, finds the most recent session across ALL projects.

    Returns:
        Path to the most recent JSONL file, or None if not found
    """
    projects_dir = get_claude_projects_dir()

    if cwd:
        # Search specific project
        project_name = cwd_to_project_dir(cwd)
        project_dir = projects_dir / project_name

        if not project_dir.exists():
            return None

        jsonl_files = list(project_dir.glob("*.jsonl"))
    else:
        # Search ALL projects for the most recent session
        if not projects_dir.exists():
            return None

        jsonl_files = list(projects_dir.rglob("*.jsonl"))

    if not jsonl_files:
        return None

    # Sort by modification time, most recent first
    jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonl_files[0]


def parse_jsonl_to_markdown(jsonl_path: Path) -> str:
    """Parse a Claude Code JSONL transcript file to readable markdown.

    Args:
        jsonl_path: Path to the JSONL file

    Returns:
        Markdown formatted transcript
    """
    messages = []

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                messages.append(obj)
            except json.JSONDecodeError:
                continue

    # Build markdown output
    md_parts = []

    for msg in messages:
        msg_type = msg.get("type", "")

        # Skip metadata entries
        if msg_type in ("summary", "file-history-snapshot"):
            continue

        if msg_type == "user":
            message_data = msg.get("message", {})
            content = message_data.get("content", "")

            # Handle different content formats
            if isinstance(content, str):
                md_parts.append(f"## Human\n\n{content}\n")
            elif isinstance(content, list):
                # Content array (tool results, etc.)
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            md_parts.append(f"## Human\n\n{item.get('text', '')}\n")
                        elif item.get("type") == "tool_result":
                            tool_content = item.get("content", "")
                            if isinstance(tool_content, list):
                                for tc in tool_content:
                                    if isinstance(tc, dict) and tc.get("type") == "text":
                                        md_parts.append(f"### Tool Result\n\n```\n{tc.get('text', '')}\n```\n")
                            else:
                                md_parts.append(f"### Tool Result\n\n```\n{tool_content}\n```\n")

        elif msg_type == "assistant":
            message_data = msg.get("message", {})
            content = message_data.get("content", [])

            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")

                        if item_type == "text":
                            md_parts.append(f"## Claude\n\n{item.get('text', '')}\n")

                        elif item_type == "thinking":
                            # Extended thinking (Ctrl+O content)
                            md_parts.append(f"## Claude (Thinking)\n\n> {item.get('thinking', '')}\n")

                        elif item_type == "tool_use":
                            tool_name = item.get("name", "unknown")
                            tool_input = item.get("input", {})
                            md_parts.append(f"### Tool Use: {tool_name}\n\n```json\n{json.dumps(tool_input, indent=2)}\n```\n")

        elif msg_type == "system":
            subtype = msg.get("subtype", "")
            content = msg.get("content", "")
            if content and subtype:
                md_parts.append(f"## System ({subtype})\n\n{content}\n")

    return "\n".join(md_parts)


def get_transcripts_dir() -> Path:
    """Get the transcripts directory from env or default to ~/transcripts"""
    env_path = os.environ.get("TRANSCRIPTS_DIR")
    if env_path:
        return Path(env_path)
    return Path.home() / "transcripts"


def ensure_month_dir(base_dir: Path, dt: datetime) -> Path:
    """Ensure year/month directory exists and return it"""
    year_dir = base_dir / str(dt.year)
    month_dir = year_dir / f"{dt.month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)
    return month_dir


def generate_filename(dt: datetime, title: Optional[str] = None) -> str:
    """Generate timestamped filename"""
    timestamp = dt.strftime("%Y-%m-%d_%H-%M-%S")
    if title:
        # Sanitize title for filename
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)
        safe_title = safe_title.strip().replace(" ", "-")[:50]
        return f"{timestamp}_{safe_title}.md"
    return f"{timestamp}.md"


def create_server() -> Server:
    """Create and configure the MCP server"""
    server = Server("transcript-saver")

    # ============================================================
    # TOOLS - Callable functions for saving transcripts
    # ============================================================

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available transcript tools"""
        return [
            Tool(
                name="save_transcript",
                description=(
                    "Save a transcript to a timestamped markdown file. "
                    "Content is saved to ~/transcripts/YYYY/MM/ with timestamp filename. "
                    "Use this to archive conversation sessions, walking journeys, and explorations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The full transcript content to save (markdown format)"
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional title for the transcript (used in filename and header)"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags for categorizing the transcript"
                        },
                        "summary": {
                            "type": "string",
                            "description": "Optional brief summary of the conversation"
                        }
                    },
                    "required": ["content"]
                }
            ),
            Tool(
                name="list_transcripts",
                description=(
                    "List saved transcripts. "
                    "Returns list of transcript files with dates and titles."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "Filter by year (e.g., 2025)"
                        },
                        "month": {
                            "type": "integer",
                            "description": "Filter by month (1-12)",
                            "minimum": 1,
                            "maximum": 12
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 20)",
                            "minimum": 1,
                            "maximum": 100
                        }
                    }
                }
            ),
            Tool(
                name="read_transcript",
                description="Read the content of a specific transcript by filename or path",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Filename or relative path of the transcript to read"
                        }
                    },
                    "required": ["filename"]
                }
            ),
            Tool(
                name="get_transcripts_path",
                description="Get the current transcripts directory path",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="save_current_session",
                description=(
                    "Automatically save the current Claude Code session transcript. "
                    "Reads the active JSONL session file, parses all messages including "
                    "extended thinking (Ctrl+O), and saves as formatted markdown. "
                    "Use this before context compacting to preserve the full conversation. "
                    "No parameters required - automatically finds the most recent session."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Optional title for the transcript"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags for categorizing the transcript"
                        },
                        "include_raw": {
                            "type": "boolean",
                            "description": "Also save the raw JSONL file (default: false)"
                        }
                    }
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls"""

        if name == "save_transcript":
            try:
                content = arguments.get("content", "")
                title = arguments.get("title")
                tags = arguments.get("tags", [])
                summary = arguments.get("summary")

                if not content.strip():
                    return [TextContent(
                        type="text",
                        text=json.dumps({"error": "Content cannot be empty"}, indent=2)
                    )]

                # Get timestamp and paths
                now = datetime.now()
                base_dir = get_transcripts_dir()
                month_dir = ensure_month_dir(base_dir, now)
                filename = generate_filename(now, title)
                filepath = month_dir / filename

                # Build markdown content with frontmatter
                md_parts = []

                # YAML frontmatter
                md_parts.append("---")
                md_parts.append(f"date: {now.isoformat()}")
                if title:
                    md_parts.append(f"title: \"{title}\"")
                if tags:
                    md_parts.append(f"tags: [{', '.join(tags)}]")
                if summary:
                    md_parts.append(f"summary: \"{summary}\"")
                md_parts.append("---")
                md_parts.append("")

                # Title header
                if title:
                    md_parts.append(f"# {title}")
                    md_parts.append("")
                    md_parts.append(f"*Saved: {now.strftime('%Y-%m-%d %H:%M:%S')}*")
                else:
                    md_parts.append(f"# Transcript - {now.strftime('%Y-%m-%d %H:%M:%S')}")
                md_parts.append("")

                # Summary if provided
                if summary:
                    md_parts.append("## Summary")
                    md_parts.append("")
                    md_parts.append(summary)
                    md_parts.append("")

                # Main content
                md_parts.append("## Transcript")
                md_parts.append("")
                md_parts.append(content)

                # Write file
                full_content = "\n".join(md_parts)
                filepath.write_text(full_content, encoding="utf-8")

                result = {
                    "status": "saved",
                    "filepath": str(filepath),
                    "filename": filename,
                    "timestamp": now.isoformat(),
                    "size_bytes": len(full_content.encode("utf-8")),
                    "title": title,
                    "tags": tags
                }

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, indent=2)
                )]

        elif name == "list_transcripts":
            try:
                year_filter = arguments.get("year")
                month_filter = arguments.get("month")
                limit = arguments.get("limit", 20)

                base_dir = get_transcripts_dir()

                if not base_dir.exists():
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "transcripts": [],
                            "total": 0,
                            "directory": str(base_dir),
                            "message": "No transcripts directory yet"
                        }, indent=2)
                    )]

                transcripts = []

                # Determine which directories to scan
                if year_filter and month_filter:
                    search_dirs = [base_dir / str(year_filter) / f"{month_filter:02d}"]
                elif year_filter:
                    year_dir = base_dir / str(year_filter)
                    search_dirs = sorted(year_dir.glob("*")) if year_dir.exists() else []
                else:
                    # All years and months
                    search_dirs = []
                    for year_dir in sorted(base_dir.glob("*"), reverse=True):
                        if year_dir.is_dir() and year_dir.name.isdigit():
                            for month_dir in sorted(year_dir.glob("*"), reverse=True):
                                if month_dir.is_dir():
                                    search_dirs.append(month_dir)

                # Collect transcript files
                for dir_path in search_dirs:
                    if not dir_path.exists():
                        continue
                    for md_file in sorted(dir_path.glob("*.md"), reverse=True):
                        if len(transcripts) >= limit:
                            break

                        # Extract info from filename
                        stat = md_file.stat()
                        transcripts.append({
                            "filename": md_file.name,
                            "path": str(md_file.relative_to(base_dir)),
                            "full_path": str(md_file),
                            "size_bytes": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })

                    if len(transcripts) >= limit:
                        break

                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "transcripts": transcripts,
                        "total": len(transcripts),
                        "directory": str(base_dir),
                        "filters": {
                            "year": year_filter,
                            "month": month_filter,
                            "limit": limit
                        }
                    }, indent=2)
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, indent=2)
                )]

        elif name == "read_transcript":
            try:
                filename = arguments.get("filename", "")

                if not filename:
                    return [TextContent(
                        type="text",
                        text=json.dumps({"error": "Filename is required"}, indent=2)
                    )]

                base_dir = get_transcripts_dir()

                # Try as relative path first
                filepath = base_dir / filename

                # If not found, search for the filename
                if not filepath.exists():
                    found_files = list(base_dir.rglob(filename))
                    if found_files:
                        filepath = found_files[0]
                    else:
                        return [TextContent(
                            type="text",
                            text=json.dumps({
                                "error": f"Transcript not found: {filename}",
                                "searched_in": str(base_dir)
                            }, indent=2)
                        )]

                content = filepath.read_text(encoding="utf-8")

                return [TextContent(
                    type="text",
                    text=content
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, indent=2)
                )]

        elif name == "get_transcripts_path":
            try:
                base_dir = get_transcripts_dir()
                exists = base_dir.exists()

                result = {
                    "path": str(base_dir),
                    "exists": exists,
                    "env_var": "TRANSCRIPTS_DIR",
                    "current_env_value": os.environ.get("TRANSCRIPTS_DIR")
                }

                if exists:
                    # Count transcripts
                    count = len(list(base_dir.rglob("*.md")))
                    result["transcript_count"] = count

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, indent=2)
                )]

        elif name == "save_current_session":
            try:
                title = arguments.get("title")
                tags = arguments.get("tags", [])
                include_raw = arguments.get("include_raw", False)

                # Find the most recent session's JSONL file (across all projects)
                jsonl_path = find_current_session_jsonl()

                if not jsonl_path:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": "Could not find any session files",
                            "searched_in": str(get_claude_projects_dir())
                        }, indent=2)
                    )]

                # Parse JSONL to markdown
                markdown_content = parse_jsonl_to_markdown(jsonl_path)

                # Get timestamp and paths
                now = datetime.now()
                base_dir = get_transcripts_dir()
                month_dir = ensure_month_dir(base_dir, now)

                # Generate title from session if not provided
                if not title:
                    title = f"Session {jsonl_path.stem}"

                filename = generate_filename(now, title)
                filepath = month_dir / filename

                # Build markdown file with frontmatter
                md_parts = []
                # Extract project name from jsonl path (parent folder name)
                project_name = jsonl_path.parent.name

                md_parts.append("---")
                md_parts.append(f"date: {now.isoformat()}")
                md_parts.append(f"title: \"{title}\"")
                md_parts.append(f"session_file: \"{jsonl_path.name}\"")
                md_parts.append(f"project: \"{project_name}\"")
                if tags:
                    md_parts.append(f"tags: [{', '.join(tags)}]")
                md_parts.append("---")
                md_parts.append("")
                md_parts.append(f"# {title}")
                md_parts.append("")
                md_parts.append(f"*Saved: {now.strftime('%Y-%m-%d %H:%M:%S')}*")
                md_parts.append(f"*Source: {jsonl_path.name}*")
                md_parts.append("")
                md_parts.append("---")
                md_parts.append("")
                md_parts.append(markdown_content)

                full_content = "\n".join(md_parts)
                filepath.write_text(full_content, encoding="utf-8")

                result = {
                    "status": "saved",
                    "filepath": str(filepath),
                    "filename": filename,
                    "timestamp": now.isoformat(),
                    "size_bytes": len(full_content.encode("utf-8")),
                    "source_jsonl": str(jsonl_path),
                    "title": title,
                    "tags": tags
                }

                # Optionally save raw JSONL too
                if include_raw:
                    import shutil
                    raw_filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_raw.jsonl"
                    raw_filepath = month_dir / raw_filename
                    shutil.copy2(jsonl_path, raw_filepath)
                    result["raw_jsonl_saved"] = str(raw_filepath)

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, indent=2)
                )]

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"}, indent=2)
            )]

    # ============================================================
    # RESOURCES - Readable state/data
    # ============================================================

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources"""
        return [
            Resource(
                uri="transcript://config",
                name="Transcript Saver Configuration",
                description="Current configuration for transcript saving",
                mimeType="application/json"
            ),
            Resource(
                uri="transcript://recent",
                name="Recent Transcripts",
                description="List of recently saved transcripts",
                mimeType="application/json"
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read resource content"""

        if uri == "transcript://config":
            base_dir = get_transcripts_dir()
            config = {
                "transcripts_directory": str(base_dir),
                "directory_exists": base_dir.exists(),
                "organization": "YYYY/MM/filename.md",
                "filename_format": "YYYY-MM-DD_HH-MM-SS_<title>.md",
                "env_var": "TRANSCRIPTS_DIR",
                "env_value": os.environ.get("TRANSCRIPTS_DIR")
            }
            return json.dumps(config, indent=2)

        elif uri == "transcript://recent":
            base_dir = get_transcripts_dir()
            if not base_dir.exists():
                return json.dumps({"transcripts": [], "message": "No transcripts yet"}, indent=2)

            # Get 10 most recent
            all_files = list(base_dir.rglob("*.md"))
            all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

            recent = []
            for f in all_files[:10]:
                stat = f.stat()
                recent.append({
                    "filename": f.name,
                    "path": str(f.relative_to(base_dir)),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

            return json.dumps({"transcripts": recent, "total_in_archive": len(all_files)}, indent=2)

        else:
            return f"Unknown resource: {uri}"

    return server


async def main():
    """Main entry point for MCP server"""
    server = create_server()

    # Run server using stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())

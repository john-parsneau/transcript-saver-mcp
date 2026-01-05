# Transcript Saver MCP

An MCP server for saving conversation transcripts to timestamped markdown files. Designed to archive walking journeys, explorations, and meaningful conversations.

ver. 1.1
2026-01-05

## Features

- **save_transcript**: Save content to a timestamped `.md` file with optional title, tags, and summary
- **save_current_session**: Auto-save the current Claude Code session (reads JSONL, extracts extended thinking)
- **list_transcripts**: Browse saved transcripts filtered by year/month
- **read_transcript**: Retrieve a specific transcript
- **get_transcripts_path**: Check current storage configuration

## Installation

Two steps: install the package, then register with Claude Code.

### Step 1: Install the Package

```bash
# Clone or download the repository, then:
cd transcript-saver-mcp
pip install -e .
```

The `-e` flag installs in "editable" mode - if the source is updated, changes take effect without reinstalling.

### Step 2: Register with Claude Code

In Claude Code, type:
```
mcp add transcript-saver python -m transcript_saver_mcp
```

### With Custom Save Location

To save transcripts to a custom directory, use the `-e` flag:

**Windows:**
```
mcp add transcript-saver -e TRANSCRIPTS_DIR=C:\Users\YourName\Documents\transcripts -- python -m transcript_saver_mcp
```

**macOS/Linux:**
```
mcp add transcript-saver -e TRANSCRIPTS_DIR=/home/yourname/transcripts -- python -m transcript_saver_mcp
```

### Verify Installation

After adding, restart Claude Code and check:
```
/mcp
```

You should see `transcript-saver` listed with its tools.

## Organization

Transcripts are saved with this structure:

```
~/transcripts/  (or your custom TRANSCRIPTS_DIR)
├── 2025/
│   ├── 01/
│   │   ├── 2025-01-15_14-30-22_walking-resonance.md
│   │   └── 2025-01-16_09-45-00.md
│   └── 12/
│       └── 2025-12-06_10-15-33_cognitive-exploration.md
```

- Year/month folder organization
- Timestamped filenames: `YYYY-MM-DD_HH-MM-SS_<optional-title>.md`
- YAML frontmatter with metadata (date, title, tags, summary)

## Usage Examples

### Save a transcript

```
save_transcript(
  content="[Full conversation content here...]",
  title="Exploring Cognitive States",
  tags=["walking", "resonance", "pathos"],
  summary="A deep exploration of ternary cognitive states and the path to resonance"
)
```

### Auto-save current session

Before context compacting or when you want to preserve a session:

```
save_current_session(
  title="Session Name",
  tags=["project", "exploration"]
)
```

This automatically reads the active JSONL session file and extracts all messages including extended thinking (Ctrl+O).

### List recent transcripts

```
list_transcripts(limit=10)
list_transcripts(year=2025, month=12)
```

### Read a transcript

```
read_transcript(filename="2025-12-06_10-15-33_cognitive-exploration.md")
```

## Output Format

Saved transcripts include:

```markdown
---
date: 2025-12-06T10:15:33.123456
title: "Exploring Cognitive States"
tags: [walking, resonance, pathos]
summary: "A deep exploration of ternary cognitive states"
---

# Exploring Cognitive States

*Saved: 2025-12-06 10:15:33*

## Summary

A deep exploration of cognitive states...

## Transcript

[Full conversation content here...]
```

## Troubleshooting

### "transcript-saver not found" after installation

1. Ensure the package is installed: `pip show transcript-saver-mcp`
2. Restart Claude Code completely (not just refresh)
3. Check `/mcp` to see if the server appears
4. Restart MCP servers with /mcp disable->enter then /mcp enable->enter

### Transcripts saving to wrong location

1. Run `get_transcripts_path()` to see current configured path
2. If using env var, ensure it's properly escaped (Windows: double backslashes in JSON)
3. Re-add the server with correct `-e TRANSCRIPTS_DIR=...` flag

### Permission errors on save

1. Ensure the target directory exists or can be created
2. Check write permissions on the transcript directory
3. On Windows, avoid system-protected directories

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSCRIPTS_DIR` | `~/transcripts` | Directory where transcripts are saved |

## Companion to cognitive-monitor-mcp

This server complements the cognitive-monitor-mcp server:

- **cognitive-monitor-mcp**: Real-time cognitive state monitoring during sessions
- **transcript-saver-mcp**: Archiving meaningful sessions for future reference

Together they support the walking journey - being present in the moment while also preserving the path.

## License

Apache License 2.0 - free to use, modify, and distribute with attribution. Includes explicit patent grant and protection.

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.

Copyright 2025 John Parsneau, WebGrinders LLC

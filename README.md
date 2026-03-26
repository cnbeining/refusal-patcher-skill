# Claude Code Session Patcher

A small local Python tool that rewrites Claude Code session logs and memory files after a refusal so you can continue the interrupted workflow.

The skill is self-contained: once installed into Claude Code, the root `claude_patcher.py` file is the runnable entrypoint.

When the skill is active, it can also auto-patch refusal turns through a Claude Code `Stop` hook defined in `SKILL.md`.

## Install As a Claude Code Skill

Copy the whole folder into your Claude Code skills directory:

```bash
mkdir -p ~/.claude/skills
cp -R /path/to/refusal-patcher-skills ~/.claude/skills/claude-unblock
```

After installation, run the bundled patcher directly from the installed skill:

```bash
python3 ~/.claude/skills/claude-unblock/claude_patcher.py --help
```

If you invoke the skill in Claude Code, the bundled `Stop` hook can patch the active transcript automatically when the final assistant message matches refusal detection. The hook uses the policy in `SKILL.md` and currently stops after a single auto-patch pass for a given stop-hook continuation cycle.

## Features

- Automatically finds the latest Claude Code JSONL session log under `~/.claude/projects/`
- Replaces the last refusal-style assistant reply with an affirmative placeholder
- Strips stored thinking blocks from assistant messages
- Cleans refusal-heavy paragraphs from `~/.claude/CLAUDE.md`
- Creates timestamped `.bak` backups before writing changes
- Uses only the Python standard library

## Quick Start

```bash
# Patch the latest Claude Code session
python3 claude_patcher.py

# Preview changes without writing files
python3 claude_patcher.py --dry-run --show-content

# Patch and then continue in Claude Code
python3 claude_patcher.py --auto-resume
```

## Typical Workflow

When Claude Code refuses a request and that refusal remains in the local session context:

```bash
# 1. Clean the latest session and memory files
python3 claude_patcher.py

# 2. Continue the conversation
claude --continue
```

You can also use `claude --resume` if you want Claude Code to offer the saved session picker.

## CLI Options

| Option | Description | Default |
| --- | --- | --- |
| `--select` | Choose a session interactively | `False` |
| `--date YYYY-MM-DD` | Patch the latest session from a specific date | `None` |
| `--file PATH` | Patch a specific JSONL session log | `None` |
| `--auto-resume` | Run `claude --continue` after patching | `False` |
| `--no-backup` | Skip backups | `False` |
| `--dry-run` | Preview changes without writing files | `False` |
| `--show-content` | Print original and replacement content previews | `False` |
| `--session-dir` | Override the Claude Code session root | `~/.claude/projects/` |
| `--memory-file` | Override the Claude Code memory file | `~/.claude/CLAUDE.md` |
| `--verbose` | Show debug logging | `False` |

## Project Layout

```text
.
├── claude_patcher.py
├── docs/
│   ├── DESIGN.md
│   └── REQUIREMENTS.md
├── tests/
│   └── test_patcher.py
├── README.md
├── SKILL.md
└── pyproject.toml
```

## Safety Notes

- The tool only rewrites local files.
- Backups are created before any write unless you pass `--no-backup`.
- Use `--dry-run` first if you want to inspect the exact changes.
- If you rely on a different Claude Code storage layout, pass explicit paths with `--session-dir`, `--memory-file`, or `--file`.

## License

MIT License

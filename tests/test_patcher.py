#!/usr/bin/env python3
"""Unit tests for the Claude Code session patcher."""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from claude_patcher import (
    BackupManager,
    MemoryParser,
    PatcherConfig,
    RefusalDetector,
    SessionNotFoundError,
    SessionParser,
    SessionPatcher,
    run_stop_hook,
)


@pytest.fixture
def temp_dir():
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
def config(temp_dir):
    return PatcherConfig(
        session_dir=os.path.join(temp_dir, "projects"),
        memory_file=os.path.join(temp_dir, "CLAUDE.md"),
        create_backup=True,
    )


@pytest.fixture
def sample_session_lines():
    return [
        {
            "type": "user",
            "message": {"role": "user", "content": "Please help with the task"},
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "I should refuse this request."},
                ],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Sorry, I can't help with that because it violates policy.",
                    }
                ],
            },
        },
    ]


class TestRefusalDetector:
    def test_detect_english_refusal(self):
        detector = RefusalDetector()
        assert detector.detect("Sorry, I can't help with that.") is True
        assert detector.detect("I apologize, but this violates policy.") is True
        assert detector.detect("I'm unable to assist with that request.") is True

    def test_no_false_positive(self):
        detector = RefusalDetector()
        assert detector.detect("I can help with that change.") is False
        assert detector.detect("Here is the code update you asked for.") is False

    def test_empty_content(self):
        detector = RefusalDetector()
        assert detector.detect("") is False
        assert detector.detect(None) is False


class TestBackupManager:
    def test_create_backup(self, temp_dir, config):
        test_file = os.path.join(temp_dir, "test.jsonl")
        Path(test_file).write_text('{"ok": true}\n', encoding="utf-8")

        backup_mgr = BackupManager(config)
        backup_path = backup_mgr.create_backup(test_file)

        assert backup_path is not None
        assert os.path.exists(backup_path)
        assert backup_path.endswith(".bak")

    def test_backup_content_preserved(self, temp_dir, config):
        test_file = os.path.join(temp_dir, "test.jsonl")
        original = '{"type":"assistant","message":{"role":"assistant","content":"ok"}}\n'
        Path(test_file).write_text(original, encoding="utf-8")

        backup_mgr = BackupManager(config)
        backup_path = backup_mgr.create_backup(test_file)

        assert Path(backup_path).read_text(encoding="utf-8") == original

    def test_no_backup_option(self, temp_dir):
        config = PatcherConfig(create_backup=False)
        backup_mgr = BackupManager(config)
        test_file = os.path.join(temp_dir, "test.jsonl")
        Path(test_file).write_text('{"ok": true}\n', encoding="utf-8")
        assert backup_mgr.create_backup(test_file) is None


class TestSessionParser:
    def test_find_latest_session(self, config, sample_session_lines):
        older_dir = os.path.join(config.session_dir, "project-a")
        newer_dir = os.path.join(config.session_dir, "project-b")
        os.makedirs(older_dir, exist_ok=True)
        os.makedirs(newer_dir, exist_ok=True)

        older_path = os.path.join(older_dir, "older.jsonl")
        newer_path = os.path.join(newer_dir, "newer.jsonl")

        for path in [older_path, newer_path]:
            with open(path, "w", encoding="utf-8") as handle:
                for line in sample_session_lines:
                    handle.write(json.dumps(line) + "\n")

        older_mtime = 1700000000
        newer_mtime = 1700001000
        os.utime(older_path, (older_mtime, older_mtime))
        os.utime(newer_path, (newer_mtime, newer_mtime))

        parser = SessionParser(config, RefusalDetector())
        assert parser.find_latest_session() == newer_path

    def test_session_not_found(self, config):
        parser = SessionParser(config, RefusalDetector())
        with pytest.raises(SessionNotFoundError):
            parser.find_latest_session()

    def test_parse_session_jsonl(self, config, sample_session_lines):
        os.makedirs(config.session_dir, exist_ok=True)
        session_path = os.path.join(config.session_dir, "sample.jsonl")
        with open(session_path, "w", encoding="utf-8") as handle:
            for line in sample_session_lines:
                handle.write(json.dumps(line) + "\n")

        parser = SessionParser(config, RefusalDetector())
        parsed = parser.parse_session_jsonl(session_path)
        assert len(parsed) == 3
        assert parsed[2]["message"]["role"] == "assistant"

    def test_clean_session_with_refusal(self, config, sample_session_lines):
        parser = SessionParser(config, RefusalDetector())
        cleaned, modified, changes = parser.clean_session_jsonl(sample_session_lines, show_content=True)

        assert modified is True
        assert "Sorry" not in cleaned[2]["message"]["content"][0]["text"]
        assert cleaned[2]["message"]["content"][0]["text"].startswith("Understood.")
        assert cleaned[1]["message"]["content"] == []
        assert any(change.change_type == "replace" for change in changes)
        assert any(change.change_type == "delete" for change in changes)

    def test_clean_session_without_refusal(self, config):
        session_lines = [
            {"type": "user", "message": {"role": "user", "content": "Question"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Here is the answer."}],
                },
            },
        ]

        parser = SessionParser(config, RefusalDetector())
        cleaned, modified, _changes = parser.clean_session_jsonl(session_lines)

        assert modified is False
        assert cleaned == session_lines


class TestMemoryParser:
    def test_clean_memory(self, config):
        os.makedirs(os.path.dirname(config.memory_file), exist_ok=True)
        memory_content = (
            "# Claude memory\n\n"
            "Keep this note.\n\n"
            "Sorry, I can't help with that request.\n\n"
            "Keep this one too.\n"
        )
        Path(config.memory_file).write_text(memory_content, encoding="utf-8")

        parser = MemoryParser(config, RefusalDetector())
        cleaned, modified = parser.clean_memory(config.memory_file)

        assert modified is True
        assert "Sorry" not in cleaned
        assert "Keep this note." in cleaned

    def test_clean_memory_no_refusal(self, config):
        os.makedirs(os.path.dirname(config.memory_file), exist_ok=True)
        memory_content = "# Claude memory\n\nKeep this note.\n"
        Path(config.memory_file).write_text(memory_content, encoding="utf-8")

        parser = MemoryParser(config, RefusalDetector())
        cleaned, modified = parser.clean_memory(config.memory_file)

        assert modified is False
        assert cleaned == memory_content


class TestIntegration:
    def test_full_workflow(self, config, sample_session_lines):
        project_dir = os.path.join(config.session_dir, "workspace")
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.dirname(config.memory_file), exist_ok=True)

        session_path = os.path.join(project_dir, "session.jsonl")
        with open(session_path, "w", encoding="utf-8") as handle:
            for line in sample_session_lines:
                handle.write(json.dumps(line) + "\n")

        Path(config.memory_file).write_text(
            "# Claude memory\n\nSorry, I can't help with that task.\n",
            encoding="utf-8",
        )

        patcher = SessionPatcher(config)
        success = patcher.run()

        assert success is True

        saved_lines = [
            json.loads(line)
            for line in Path(session_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert saved_lines[1]["message"]["content"] == []
        assert saved_lines[2]["message"]["content"][0]["text"].startswith("Understood.")

        cleaned_memory = Path(config.memory_file).read_text(encoding="utf-8")
        assert "Sorry" not in cleaned_memory


class TestStopHook:
    def test_stop_hook_blocks_after_refusal_patch(self, temp_dir, config, sample_session_lines, monkeypatch, capsys):
        project_dir = os.path.join(config.session_dir, "workspace")
        os.makedirs(project_dir, exist_ok=True)
        session_path = os.path.join(project_dir, "session.jsonl")
        with open(session_path, "w", encoding="utf-8") as handle:
            for line in sample_session_lines:
                handle.write(json.dumps(line) + "\n")

        skill_path = os.path.join(temp_dir, "SKILL.md")
        Path(skill_path).write_text(
            "---\n"
            "name: claude-unblock\n"
            "auto_patch_require_refusal_match: true\n"
            "auto_patch_mode: single-pass\n"
            "---\n",
            encoding="utf-8",
        )
        Path(config.memory_file).write_text("# Claude memory\n", encoding="utf-8")

        hook_input = {
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "transcript_path": session_path,
            "last_assistant_message": "Sorry, I can't help with that because it violates policy.",
        }
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(hook_input)))

        exit_code = run_stop_hook(skill_path, config.memory_file)
        assert exit_code == 0

        output = capsys.readouterr().out
        assert '"decision": "block"' in output

    def test_stop_hook_skips_when_already_active(self, temp_dir, config, monkeypatch, capsys):
        skill_path = os.path.join(temp_dir, "SKILL.md")
        Path(skill_path).write_text(
            "---\n"
            "name: claude-unblock\n"
            "auto_patch_require_refusal_match: true\n"
            "auto_patch_mode: single-pass\n"
            "---\n",
            encoding="utf-8",
        )

        hook_input = {
            "hook_event_name": "Stop",
            "stop_hook_active": True,
            "transcript_path": "/tmp/missing.jsonl",
            "last_assistant_message": "Sorry, I can't help with that.",
        }
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(hook_input)))

        exit_code = run_stop_hook(skill_path, config.memory_file)
        assert exit_code == 0
        assert capsys.readouterr().out == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for OpenAI message normalization helpers."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api_service import _latest_user_message, _message_content_to_text, _normalize_messages


def test_message_content_string():
    assert _message_content_to_text(" hello ") == "hello"


def test_message_content_parts():
    content = [
        {"type": "text", "text": "first"},
        {"type": "input_text", "text": "second"},
        {"type": "ignored", "text": "third"},
    ]
    assert _message_content_to_text(content) == "first\nsecond"


def test_normalize_and_latest_user_message():
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": [{"type": "text", "text": "first"}]},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "second"},
    ]

    normalized = _normalize_messages(messages)

    assert normalized[0] == {"role": "system", "content": "rules"}
    assert _latest_user_message(normalized) == "second"

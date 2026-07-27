"""Test cho extract_json_object() — hàm bóc JSON dùng chung cho mọi AI chain.  #Huynh"""

import json

import pytest

from src.ai.shared.json_output import extract_json_object


class TestExtractJsonObject:
    def test_plain_json(self):
        assert extract_json_object('{"project_type": "Website"}') == {"project_type": "Website"}

    def test_fenced_json(self):
        raw = '```json\n{"project_type": "Website"}\n```'
        assert extract_json_object(raw) == {"project_type": "Website"}

    def test_preamble_before_fenced_json(self):
        """Đúng chuỗi đã làm hỏng production: câu dẫn, rồi fence không nhãn.

        llama-4-scout cứ thêm câu dẫn ở đầu. Bản cũ chỉ cắt fence khi câu trả lời
        BẮT ĐẦU bằng fence, nên ca này ném lỗi và kết quả AI hoàn toàn đúng bị vứt
        đi.  #Huynh
        """
        raw = (
            "Here is the draft qualification result:\n\n"
            "```\n"
            '{"project_type": "E-commerce Website", "suggested_lead_score": "HOT"}\n'
            "```"
        )
        assert extract_json_object(raw) == {
            "project_type": "E-commerce Website",
            "suggested_lead_score": "HOT",
        }

    def test_preamble_without_fence(self):
        assert extract_json_object('Sure! Here you go: {"project_type": "Website"}') == {
            "project_type": "Website"
        }

    def test_trailing_commentary_after_json(self):
        raw = '{"project_type": "Website"}\n\nLet me know if you need anything else!'
        assert extract_json_object(raw) == {"project_type": "Website"}

    def test_nested_objects_are_not_truncated(self):
        """Greedy quan trọng ở đây: non-greedy sẽ dừng ở dấu `}` đầu tiên.  #Huynh"""
        raw = (
            "Result:\n"
            '{"detected_signals": [{"text": "Clear budget", "is_positive": true}], '
            '"price_range_min": 40000000}'
        )
        assert extract_json_object(raw) == {
            "detected_signals": [{"text": "Clear budget", "is_positive": True}],
            "price_range_min": 40000000,
        }

    def test_malformed_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json_object("not valid json")

    def test_prose_with_broken_json_still_raises(self):
        """Có khối `{...}` nhưng JSON hỏng thì VẪN phải báo lỗi, không nuốt im lặng.  #Huynh"""
        with pytest.raises(json.JSONDecodeError):
            extract_json_object("Here you go: {project_type: Website,,}")

    def test_empty_string_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json_object("")

#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
from common.llm_output_sanitize import sanitize_user_facing_llm_output


def test_strips_planning_preamble_and_lets_craft():
    raw = (
        'We need to answer "whats new on my inbox". Summarize recent messages.\n'
        "Return format with Answer, Sources, Next steps.\n"
        "Let's craft.Answer\n"
        "Security alerts – two Microsoft notices.\n\n"
        "Sources\n"
        "Microsoft – login alert\n\n"
        "Next steps\n"
        "1. Verify Microsoft activity\n"
    )
    out = sanitize_user_facing_llm_output(raw)
    assert "We need to answer" not in out
    assert "Let's craft" not in out
    assert out.startswith("Security alerts")


def test_strips_redacted_thinking_block():
    raw = "<think>planning</think>\n## Threat board\nT3 item"
    out = sanitize_user_facing_llm_output(raw)
    assert "planning" not in out
    assert out.startswith("## Threat board")

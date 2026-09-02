"""飞书私聊通知：只构造 lark-cli 命令行，不直接执行。"""
from __future__ import annotations


def lark_send_args(open_id: str, markdown: str, idem_key: str) -> list:
    if not open_id:
        raise ValueError("缺少飞书 open_id（JIRA_WATCH_LARK_OPEN_ID）")
    return ["lark-cli", "im", "+messages-send", "--user-id", open_id, "--markdown", markdown,
            "--as", "bot", "--idempotency-key", idem_key]

"""通知命令构造、简报渲染、配置解析。"""
from jw import notify, brief, config


def test_lark_send_args_dm_markdown_with_idempotency():
    args = notify.lark_send_args(open_id="ou_x", markdown="**hi**", idem_key="jw-2026-09-02-1")
    assert args[:3] == ["lark-cli", "im", "+messages-send"]
    assert "--user-id" in args and args[args.index("--user-id") + 1] == "ou_x"
    assert "--markdown" in args and "--as" in args and args[args.index("--as") + 1] == "bot"
    assert args[args.index("--idempotency-key") + 1] == "jw-2026-09-02-1"


def test_lark_send_args_requires_open_id():
    try:
        notify.lark_send_args(open_id="", markdown="x", idem_key="k")
    except ValueError as e:
        assert "open_id" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_render_brief_sections_and_pending():
    r = {
        "round_id": "2026-09-02T08:00:00Z",
        "mode": "OBSERVE",
        "events_total": 3,
        "verdicts": [{"key": "CIR-1", "category": "CUSTOMER_BUG", "verdict": "AI_VERIFIED", "evidence": "PR #1 on master"}],
        "actions": [{"key": "CIR-1", "action": "COMMENT", "confirmation": "comment 123"}],
        "pending_user": [{"key": "CIR-2", "why": "无法解析版本"}],
        "gaps": ["internal-core 克隆陈旧 6 天"],
        "next_interval": "30m",
    }
    out = brief.render_brief(r)
    for marker in ("①", "②", "③", "④", "⑤", "⑥"):
        assert marker in out
    assert "CIR-2" in out and "无法解析版本" in out
    assert "30m" in out


def test_parse_shell_conf_quotes_and_comments():
    text = 'A="x y"\nB=\'p+q#z\'\n# c\nC=plain\n\nD=""\n'
    assert config.parse_shell_conf(text) == {"A": "x y", "B": "p+q#z", "C": "plain", "D": ""}


def test_defaults_and_overrides():
    cfg = config.build_config({"JIRA_URL": "http://j", "JIRA_USER": "u", "JIRA_TOKEN": "t"}, {"JIRA_WATCH_MODE": "INTERACT"})
    assert cfg.mode == "INTERACT"
    assert cfg.jql.startswith("assignee = currentUser()")
    assert cfg.bot_users == ("aibot",)
    assert cfg.allowed_transitions == ("处理中",)
    assert cfg.jira_url == "http://j"


def test_config_rejects_unknown_mode():
    try:
        config.build_config({"JIRA_URL": "h", "JIRA_USER": "u", "JIRA_TOKEN": "t"}, {"JIRA_WATCH_MODE": "GODMODE"})
    except ValueError as e:
        assert "mode" in str(e).lower()
    else:
        raise AssertionError("expected ValueError")


def test_config_requires_jira_credentials():
    try:
        config.build_config({}, {})
    except ValueError as e:
        assert "JIRA_TOKEN" in str(e) or "JIRA_URL" in str(e)
    else:
        raise AssertionError("expected ValueError")

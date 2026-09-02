"""附件下载守卫：路径穿越、非本站 URL。"""
from jw import cli


def test_attachment_url_outside_jira_host_is_skipped():
    assert cli.attachment_url_allowed("http://j/secure/attachment/1/x.log", "http://j") is True
    assert cli.attachment_url_allowed("http://evil/secure/attachment/1/x.log", "http://j") is False
    assert cli.attachment_url_allowed("http://j.evil/x", "http://j") is False

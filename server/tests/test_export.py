"""提报人补充原话聚合（方案乙）：user_supplements 过滤规则与 to_markdown 补充原话节排版。"""
from app.services.export import to_markdown, user_supplements


def _msg(role, content, created_at="2026-10-08 09:31:00"):
    return {"role": role, "content": content, "createdAt": created_at}


def test_user_supplements_excludes_a8_base_and_assistant():
    messages = [
        _msg("USER", "我要做个海报生成智能体，给市场部用", "2026-10-08 09:30:00"),
        _msg("ASSISTANT", "这个需求有多紧急？", "2026-10-08 09:30:10"),
        _msg("USER", "紧急，本周内要", "2026-10-08 09:31:00"),
        _msg("ASSISTANT", "希望达成什么业务目标？", "2026-10-08 09:31:10"),
        _msg("USER", "提升市场部出图效率", "2026-10-08 09:32:00"),
    ]
    supplements = user_supplements("我要做个海报生成智能体，给市场部用", messages)
    assert [m["content"] for m in supplements] == ["紧急，本周内要", "提升市场部出图效率"]


def test_user_supplements_only_skip_first_identical_message():
    # 用户两轮发了相同文本：仅首条（A8 底稿）被排除，第二条仍是补充原话
    messages = [_msg("USER", "同样的话", "2026-10-08 09:30:00"), _msg("USER", "同样的话", "2026-10-08 09:35:00")]
    supplements = user_supplements("同样的话", messages)
    assert len(supplements) == 1 and supplements[0]["createdAt"] == "2026-10-08 09:35:00"


def test_user_supplements_all_user_messages_when_content_blank_or_manual():
    messages = [_msg("USER", "第一句"), _msg("USER", "第二句")]
    # content 为空（A8 未回填）：全部 USER 消息都是补充原话
    assert len(user_supplements(None, messages)) == 2
    # content 为用户手填（与任何消息都不全等）：同样全列
    assert len(user_supplements("手填的底稿", messages)) == 2


def test_to_markdown_renders_supplements_section_after_a8():
    demand = {"title": "海报生成智能体", "content": "我要做个海报生成智能体", "quality": [], "fieldSources": {}, "changeLogs": []}
    messages = [
        _msg("USER", "我要做个海报生成智能体", "2026-10-08 09:30:00"),
        _msg("ASSISTANT", "有多紧急？"),
        _msg("USER", "紧急，\n本周内要", "2026-10-08 09:31:00"),
    ]
    markdown = to_markdown(demand, None, messages)
    assert "### 提报人补充原话" in markdown
    assert markdown.index("### 提报人补充原话") > markdown.index("## 原始提报文本（A8）")
    assert "- 2026-10-08 09:31:00：紧急， 本周内要" in markdown  # 换行转空格防破坏 md 列表
    assert "有多紧急？\n\n- " not in markdown  # ASSISTANT 消息不进补充原话节


def test_to_markdown_omits_section_when_no_supplements():
    demand = {"title": "t", "content": "唯一一句话", "quality": [], "fieldSources": {}, "changeLogs": []}
    markdown = to_markdown(demand, None, [_msg("USER", "唯一一句话")])
    assert "提报人补充原话" not in markdown

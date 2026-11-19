from app.ai.tool_registry import register_tool, get_tool_schemas

def test_tool_registry():
    schema = {"type":"function","function":{"name":"test_tool","parameters":{"type":"object"}}}
    register_tool(schema, lambda: None)
    assert any(item["function"]["name"] == "test_tool" for item in get_tool_schemas())

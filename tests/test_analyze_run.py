from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_tool_compiler import ATC


def test_decorate_response_extracts_tools_usage_answer_and_ratio(tmp_path):
    messages = [
        HumanMessage(content="Question"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "describe_table", "args": {"table_name": "orders"}, "id": "call_1"},
                {"name": "run_sql", "args": {"query": "select 1"}, "id": "call_2"},
            ],
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        ),
        ToolMessage(content="order_id TEXT", name="describe_table", tool_call_id="call_1"),
        ToolMessage(content="| x |\n| - |\n| 1 |", name="run_sql", tool_call_id="call_2"),
        AIMessage(content="DHL had the most delays."),
    ]
    response = ATC(project_dir=tmp_path / ".atc").decorate_response(
        "Question", {"messages": messages}
    )

    assert response["answer"] == "DHL had the most delays."
    assert response["atc"]["can_compile"] is True
    assert response["atc"]["summary"]["tool_names"] == ["describe_table", "run_sql"]
    assert response["atc"]["summary"]["total_tokens"] == 120
    assert response["atc"]["summary"]["output_tokens"] == 20
    assert response["atc"]["summary"]["work_to_answer_ratio"].endswith("x")

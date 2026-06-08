import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agent_tool_compiler import ATC  # noqa: E402
from examples.langgraph_data_agent.db.setup_demo_db import setup_demo_db  # noqa: E402
from examples.langgraph_data_agent.tools import describe_table, list_tables, run_sql  # noqa: E402

SYSTEM_PROMPT = """You are a careful logistics analytics agent.
Use tools to inspect the SQLite schema and answer with concise business summaries.

Business definitions:
- A shipment is late if delivered_date > promised_delivery_date.
- If delivered_date is NULL and promised_delivery_date < end_date, it may be potentially late.
- For date ranges use start_date inclusive and end_date exclusive.
- For "delays yesterday", filter the due date window with
  orders.promised_delivery_date >= start_date AND orders.promised_delivery_date < end_date.
- Do not filter late shipments by delivered_date for the business date window; delayed shipments may
  be delivered after the promised day.
- orders connects to shipments through order_id.
- shipments connects to carriers through carrier.
- shipments connects to warehouses through warehouse_id.
- shipments connects to tracking_events through shipment_id.
- country lives in orders.country.
- orders.service is the shipping method.
- orders.service can be STANDARD, EXPRESS, or DROPPOINT.
- "yesterday" in the demo is 2026-06-06 to 2026-06-07.
- Demo countries include Italy (IT), Spain (ES), and France (FR).
- For follow-up questions, preserve the prior country, date range, and metric unless the user
  explicitly changes them.
- If the prior question was about Italy yesterday and the user asks "what about EXPRESS?", treat
  EXPRESS as orders.service = 'EXPRESS' while preserving the prior country/date/metric.
Prefer a compiled ATC capability when one matches the question."""


def build_app():
    load_dotenv()
    setup_demo_db()
    agent_model = os.getenv("ATC_AGENT_MODEL", "gpt-4o-mini")
    compiler_model = os.getenv("ATC_COMPILER_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=agent_model, temperature=0)
    semantic_model = ChatOpenAI(model=compiler_model, temperature=0)

    # The agent itself is a LangGraph prebuilt ReAct agent. ATC sits around it:
    # atc.tools(...) registers the base LangChain tools, loads persisted
    # capabilities from .atc, and exposes those capabilities back to LangGraph
    # as normal tools. After agent.invoke(...), atc.decorate_response(...)
    # inspects the LangGraph message trace to build the compile candidate.
    atc = ATC(project_dir=".atc", semantic_model=semantic_model)
    tools = atc.tools([list_tables, describe_table, run_sql])
    agent = create_react_agent(llm, tools, prompt=SystemMessage(content=SYSTEM_PROMPT))
    return atc, agent


def ask(question: str) -> dict:
    atc, agent = build_app()
    result = agent.invoke({"messages": [("user", question)]})
    return atc.decorate_response(question=question, agent_result=result)


if __name__ == "__main__":
    response = ask("What carriers had the most delays yesterday in Italy?")
    print(response["answer"])

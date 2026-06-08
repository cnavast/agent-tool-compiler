import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from examples.langgraph_data_agent.main import build_app  # noqa: E402

load_dotenv()
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="ATC LangGraph Data Agent Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
atc, agent = build_app()


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str | None = None
    messages: list[ChatTurn] = Field(default_factory=list)

    def request_messages(self) -> list[ChatTurn]:
        if self.messages:
            return self.messages
        if self.message:
            return [ChatTurn(role="user", content=self.message)]
        raise HTTPException(status_code=400, detail="Expected message or messages.")

    def to_langgraph_messages(self) -> list[tuple[str, str]]:
        return [(_normalize_role(turn.role), turn.content) for turn in self.request_messages()]

    def latest_user_message(self) -> str:
        for turn in reversed(self.request_messages()):
            if _normalize_role(turn.role) == "user":
                return turn.content
        raise HTTPException(status_code=400, detail="Expected at least one user message.")


class CompileRequest(BaseModel):
    candidate: dict


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat")
def chat(request: ChatRequest):
    chat_messages = request.to_langgraph_messages()
    question = request.latest_user_message()
    result = agent.invoke({"messages": chat_messages})
    response = atc.decorate_response(question=question, agent_result=result)
    summary = response["atc"]["summary"]
    print(f"\nQuestion:\n{question}\n")
    print("Tools used:")
    for name in summary["tool_names"]:
        print(f"- {name}")
    print("\nToken usage:")
    print(f"- total_tokens: {summary['total_tokens']}")
    print(f"- output_tokens: {summary['output_tokens']}")
    print(f"- final_answer_tokens: {summary['final_answer_tokens']}")
    return response


def _normalize_role(role: str) -> str:
    role = role.lower()
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    raise HTTPException(status_code=400, detail=f"Unsupported chat role: {role}")


@app.post("/atc/compile")
def compile_candidate(request: CompileRequest):
    global atc, agent
    try:
        capability = atc.compile(request.candidate)
    except ValueError as exc:
        print("\nTool compile failed:")
        print(f"- error: {exc}\n")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_created_tool(capability)
    atc, agent = build_app()
    return {
        "status": "compiled",
        "capability_name": capability.name,
        "mcp_available": True,
    }


def log_created_tool(capability) -> None:
    print("\nTool created:")
    print(f"- name: {capability.name}")
    print(f"- description: {capability.description}\n")


@app.post("/reload-tools")
def reload_tools():
    global atc, agent
    atc, agent = build_app()
    return {"status": "reloaded"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("examples.langgraph_data_agent.server:app", host="127.0.0.1", port=8000, reload=False)

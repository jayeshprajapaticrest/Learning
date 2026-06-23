"""MULTI-AGENT implementation (supervisor / orchestrator pattern).

A supervisor LLM routes each turn to one specialist worker, collects its
output, and decides whether to route again or finish with a synthesized answer.
This is the canonical pattern for splitting a hard task across focused agents.

    ┌──────────────┐  route   ┌────────────┐
    │  SUPERVISOR  │ ───────▶ │  researcher │  (RAG over the knowledge base)
    │  (Opus 4.8)  │ ◀─────── │  support    │  (MCP support-ticket tools)
    │              │  result  │  calculator │  (arithmetic)
    └──────┬───────┘          └────────────┘
           │ FINISH
           ▼
    ┌──────────────┐
    │  SYNTHESIZE  │ ──▶ final answer to the user
    └──────────────┘

Each worker is itself a small ReAct agent (see single_agent.py), so this graph
composes single agents into a team.
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from .llm import supervisor_llm, worker_llm
from .memory import get_checkpointer
from .tools import calculate, knowledge_base_search, load_mcp_tools

WORKERS = ["researcher", "support", "calculator"]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    next: str


class Route(BaseModel):
    """Supervisor's routing decision."""
    next: Literal["researcher", "support", "calculator", "FINISH"]


SUPERVISOR_PROMPT = (
    "You are the supervisor of a support team. Given the conversation, decide "
    "which worker should act next, or FINISH if there is enough information to "
    "answer the user.\n"
    "- researcher: searches the internal knowledge base (product, billing, policy).\n"
    "- support: looks up / creates support tickets via external tools.\n"
    "- calculator: does arithmetic.\n"
    "Route to exactly one worker, or FINISH. Do not loop on a worker that has "
    "already answered."
)


def _make_worker(node_name: str, agent):
    """Wrap a ReAct sub-agent as a graph node.

    Runs the sub-agent over the conversation so far and appends its final
    message back to the shared state, tagged with the worker's name.
    """

    async def node(state: AgentState) -> dict:
        result = await agent.ainvoke({"messages": state["messages"]})
        last = result["messages"][-1]
        return {"messages": [AIMessage(content=last.content, name=node_name)]}

    node.__name__ = node_name
    return node


async def build_multi_agent(*, with_memory: bool = True):
    """Assemble and compile the supervisor graph."""
    mcp_tools = await load_mcp_tools()

    # Build the three specialist sub-agents (each a single ReAct agent).
    researcher = create_react_agent(
        worker_llm(), tools=[knowledge_base_search],
        prompt="You research the knowledge base and answer with citations.",
    )
    support = create_react_agent(
        worker_llm(), tools=mcp_tools,
        prompt="You handle support tickets using the available tools.",
    )
    calculator = create_react_agent(
        worker_llm(), tools=[calculate],
        prompt="You perform arithmetic and report the result.",
    )
    agents = {"researcher": researcher, "support": support, "calculator": calculator}

    router_llm = supervisor_llm().with_structured_output(Route)

    async def supervisor(state: AgentState) -> dict:
        messages = [HumanMessage(content=SUPERVISOR_PROMPT)] + state["messages"]
        decision: Route = await router_llm.ainvoke(messages)
        return {"next": decision.next}

    async def synthesize(state: AgentState) -> dict:
        prompt = (
            "Using the team's findings above, write a clear, final answer for "
            "the user. Cite knowledge-base sources where relevant."
        )
        messages = state["messages"] + [HumanMessage(content=prompt)]
        answer = await supervisor_llm().ainvoke(messages)
        return {"messages": [answer]}

    # --- Wire the graph -----------------------------------------------------
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("synthesize", synthesize)
    for name in WORKERS:
        graph.add_node(name, _make_worker(name, agents[name]))

    graph.add_edge(START, "supervisor")
    # Workers always report back to the supervisor.
    for name in WORKERS:
        graph.add_edge(name, "supervisor")

    # Supervisor decides where to go next.
    def route(state: AgentState) -> str:
        return "synthesize" if state["next"] == "FINISH" else state["next"]

    graph.add_conditional_edges(
        "supervisor", route,
        {**{w: w for w in WORKERS}, "synthesize": "synthesize"},
    )
    graph.add_edge("synthesize", END)

    checkpointer = get_checkpointer() if with_memory else None
    return graph.compile(checkpointer=checkpointer)

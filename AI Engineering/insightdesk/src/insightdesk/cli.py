"""Interactive CLI.

    python -m insightdesk.cli                 # single agent (default)
    python -m insightdesk.cli --mode multi    # supervisor multi-agent team

Conversation memory is keyed by --thread; reuse the same value to continue a
previous conversation (state is persisted to SQLite via the checkpointer).
"""
from __future__ import annotations

import argparse
import asyncio

from langchain_core.messages import HumanMessage

from .multi_agent import build_multi_agent
from .single_agent import build_single_agent


async def chat_loop(mode: str, thread: str) -> None:
    if mode == "multi":
        app = await build_multi_agent(with_memory=True)
    else:
        app = await build_single_agent(with_mcp=True, with_memory=True)

    config = {"configurable": {"thread_id": thread}}
    print(f"InsightDesk [{mode}] — thread '{thread}'. Type 'exit' to quit.\n")

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user.lower() in {"exit", "quit"}:
            break
        if not user:
            continue

        result = await app.ainvoke({"messages": [HumanMessage(content=user)]}, config)
        print(f"\nbot> {result['messages'][-1].content}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="InsightDesk assistant")
    parser.add_argument("--mode", choices=["single", "multi"], default="single")
    parser.add_argument("--thread", default="demo-thread")
    args = parser.parse_args()
    asyncio.run(chat_loop(args.mode, args.thread))


if __name__ == "__main__":
    main()

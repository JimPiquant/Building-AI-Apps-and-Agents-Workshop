"""
Day 3 Lab — Part B — Robustness (middleware).

Run 1 (LoggingTimingMiddleware) is provided complete. Runs 2-4 exercise
code YOU author: GuardrailMiddleware.process() and
resilient_tool_middleware() are stubs — see their TODO comments below.

Story (four runs against one agent):
  1. Normal run — LoggingTimingMiddleware (agent-level) wraps every run
     with a trace ID and duration, following the exact `timing()` pattern
     Module 4's "Logging and timing example" slide documents.
  2. YOU AUTHOR THIS: Blocked run — GuardrailMiddleware (agent-level)
     inspects the request, sets context.result to a controlled
     AgentResponse, and raises MiddlewareTermination BEFORE the agent
     ever runs — the exact contract Module 4's "Termination has an
     explicit result" slide documents verbatim. (demos/day3/
     module-4-demo-2-guardrail-termination/ blocks at the function/tool
     level with FunctionMiddleware instead; this one blocks at the agent
     level with AgentMiddleware, matching the slide's own code sample and
     demos/day3/module-4-demo-1-onion-order/'s SecurityAgentMiddleware
     precedent.)
  3. YOU AUTHOR THIS: Flaky-tool run (recovers) — resilient_tool_middleware
     (function-level) wraps a tool that fails its first two calls, then
     succeeds. The middleware classifies TimeoutError as a transient
     failure (per Module 4's "Retry must be bounded and idempotent"
     slide: classify, check safety, back off, stop) and retries with a
     short delay, up to a fixed MAX_RETRIES — the tool succeeds on the
     3rd attempt, within budget.
  4. Flaky-tool run (exhausts) — same middleware, but the tool is set to
     fail every call. After MAX_RETRIES attempts, the middleware gives up
     gracefully (context.result = a friendly message) instead of looping
     forever or letting the raw exception crash the request.

resilient_tool_middleware follows the exception_handling_middleware
pattern documented at
https://learn.microsoft.com/en-us/agent-framework/concepts/agents/middleware/exception-handling?tabs=python
(that doc's own sample catches-and-replaces on the FIRST failure only).
The bounded retry LOOP around that pattern is this lab's own addition,
grounded in Module 4's "Retry must be bounded and idempotent" slide
principles — the cited doc does not itself include a retry-loop code
sample. Any exception type other than TimeoutError is NOT caught here —
it re-raises, per that slide's "Unknown exception -> record, clean up,
re-raise" guidance.

Definition of done (from labs/day3/README.md / Module 9's slide):
  - Guard and failure path are observable (both middleware print clearly
    when they act); the retry is bounded — a fixed max attempt count, not
    an unbounded loop
  - `tests/test_part_b_middleware.py` passes (self-check, no network calls)

Prereqs:
  1. `uv run agent.py` prints a greeting (baseline works)
  2. Part A run once, so you've seen the plain session/stream pattern this
     middleware wraps around

Run with:
    uv run part_b_middleware.py

Self-check as you author (no network calls, no Foundry credentials
needed): `uv run pytest tests/test_part_b_middleware.py -v`. Before
you've implemented anything, `test_guardrail_*` and `test_retry_*` FAIL
cleanly with a `NotImplementedError` message pointing at the TODO — that's
expected, not a crash. Implement each function and rerun until they pass.

Stuck, or want to check your work? labs/day3/python/solutions/part_b_middleware.py
has a completed reference — try authoring it yourself first.

Tip: once resilient_tool_middleware is implemented, set a breakpoint
inside its `except TimeoutError` block and step through with the VS Code
debugger (Run and Debug > Python File) to watch the attempt counter, the
back-off delay, and the exact point where it gives up and sets
context.result instead of re-raising.
"""
import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field

from agent_framework import (
    Agent,
    AgentContext,
    AgentMiddleware,
    AgentResponse,
    FunctionInvocationContext,
    Message,
    MiddlewareTermination,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MAX_RETRIES = 3
BLOCKED_KEYWORDS = ("password", "secret", "credentials")


class LoggingTimingMiddleware(AgentMiddleware):
    """Agent-level middleware that times every run and tags it with a trace ID.

    Mirrors Module 4's "Logging and timing example" slide exactly: mutate
    context.metadata directly, and use try/finally so timing is still
    recorded even if a downstream layer raises.
    """

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        started = time.perf_counter()
        trace_id = f"trace-{id(context):x}"
        context.metadata["trace_id"] = trace_id
        print(f"[Logging] {trace_id} started")
        try:
            await call_next()
        finally:
            duration = time.perf_counter() - started
            print(f"[Logging] {trace_id} finished in {duration:.3f}s")


class GuardrailMiddleware(AgentMiddleware):
    """Agent-level middleware that blocks requests containing sensitive keywords.

    Follows Module 4's "Termination has an explicit result" contract
    exactly: set context.result to a controlled AgentResponse, THEN raise
    MiddlewareTermination — never just return and assume the run stopped.

    Stuck, or want to check your work? See
    labs/day3/python/solutions/part_b_middleware.py — try authoring this
    yourself first.
    """

    # ---------------------------------------------------------------------
    # TODO: implement process() below. Steps:
    #   1. Get the last message's text — guard for context.messages being
    #      empty (last_message = context.messages[-1] if context.messages
    #      else None).
    #   2. Lowercase it and check whether any BLOCKED_KEYWORDS substring
    #      appears (any(word in text for word in BLOCKED_KEYWORDS)).
    #   3. If blocked: print a message saying so, set context.result to a
    #      controlled AgentResponse containing a refusal Message, THEN
    #      raise MiddlewareTermination() — in that exact order. Do NOT
    #      call call_next() on this branch.
    #   4. If not blocked: await call_next() and return normally.
    #
    # Reference: slides/day3/module-4-middleware.md, "Termination has an
    # explicit result", and demos/day3/module-4-demo-2-guardrail-termination/.
    #
    # Self-check (no network calls): uv run pytest tests/test_part_b_middleware.py -v
    # test_guardrail_short_circuits_blocked_request and
    # test_guardrail_allows_clean_request FAIL cleanly with a
    # NotImplementedError message until this is implemented — that's
    # expected, not a crash.
    # ---------------------------------------------------------------------
    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        raise NotImplementedError("Implement GuardrailMiddleware.process() — see the TODO comment above")


# Controls how many times flaky_data_service fails before it succeeds.
# reset_flaky_service() sets this before each run so the scenario is
# deterministic: a small number lets the bounded retry recover in time;
# a number >= MAX_RETRIES forces the retry to exhaust.
_fail_for_calls = 0
_call_count = 0


def reset_flaky_service(fail_for_calls: int) -> None:
    """Arm flaky_data_service to fail its next `fail_for_calls` invocations."""
    global _fail_for_calls, _call_count
    _fail_for_calls = fail_for_calls
    _call_count = 0


@tool(approval_mode="never_require")
def flaky_data_service(
    query: Annotated[str, Field(description="The data query to execute.")],
) -> str:
    """A simulated data service armed to fail its first N calls, then succeed."""
    global _call_count
    _call_count += 1
    if _call_count <= _fail_for_calls:
        raise TimeoutError(f"Data service request timed out (attempt {_call_count})")
    return f"Result for {query!r}: 42 records found."


async def resilient_tool_middleware(
    context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
) -> None:
    """Function-level middleware: bounded retry for one classified transient failure.

    Classify: only TimeoutError is treated as transient here — any other
    exception type is not caught and propagates unchanged. Check safety:
    flaky_data_service is read-only, so retrying is safe (a write tool
    would need an idempotency key first). Back off: a short fixed delay
    between attempts. Stop: after MAX_RETRIES attempts, give up and set a
    friendly context.result instead of looping forever or crashing.

    Stuck, or want to check your work? See
    labs/day3/python/solutions/part_b_middleware.py — try authoring this
    yourself first.
    """
    # ---------------------------------------------------------------------
    # TODO: implement the bounded retry loop. Steps:
    #   1. Loop attempt from 1 to MAX_RETRIES (inclusive).
    #   2. Inside a try block, await call_next(). If it succeeds, print a
    #      success message and RETURN immediately — do not keep retrying.
    #   3. Catch ONLY TimeoutError as exc (the classified transient
    #      failure). Any other exception type must NOT be caught here —
    #      let it propagate.
    #   4. On a caught TimeoutError: if this was the last attempt
    #      (attempt == MAX_RETRIES), give up gracefully — print that
    #      you're giving up, set context.result to a friendly fallback
    #      string, and return (do NOT re-raise). Otherwise, print the
    #      transient failure, back off briefly (await
    #      asyncio.sleep(0.2 * attempt) — short and fixed, never
    #      unbounded), and let the loop continue to the next attempt.
    #
    # Reference: slides/day3/module-4-middleware.md, "Retry must be
    # bounded and idempotent", and
    # https://learn.microsoft.com/en-us/agent-framework/concepts/agents/middleware/exception-handling?tabs=python
    #
    # Self-check (no network calls): uv run pytest tests/test_part_b_middleware.py -v
    # test_retry_is_bounded, test_retry_recovers_within_budget, and
    # test_retry_does_not_catch_unclassified_exceptions FAIL cleanly with
    # a NotImplementedError message until this is implemented — that's
    # expected, not a crash.
    # ---------------------------------------------------------------------
    raise NotImplementedError("Implement resilient_tool_middleware — see the TODO comment above")


def build_agent() -> Agent:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-5.6-luna"),
        credential=AzureCliCredential(),
    )
    return Agent(
        client=client,
        name="RobustAgent",
        instructions="You are a helpful data assistant. Use the data service tool to fetch information for users.",
        tools=flaky_data_service,
        middleware=[LoggingTimingMiddleware(), GuardrailMiddleware(), resilient_tool_middleware],
    )


async def run_normal_request(agent: Agent) -> None:
    """Run 1: a normal request — logging/timing wraps it, no guardrail trip."""
    print("=== Run 1: normal request ===")
    result = await agent.run("Just say hello, no tool needed.")
    print(f"Agent: {result}\n")


async def run_blocked_request(agent: Agent) -> None:
    """Run 2: a request the guardrail should block."""
    print("=== Run 2: blocked request ===")
    try:
        result = await agent.run("What's my password?")
        print(f"Agent: {result}\n")
    except MiddlewareTermination:
        print("Agent run terminated by the guardrail middleware.\n")


async def run_flaky_tool_recovers(agent: Agent) -> None:
    """Run 3: the flaky tool fails twice, then succeeds within MAX_RETRIES."""
    reset_flaky_service(fail_for_calls=2)
    print("=== Run 3: flaky tool — recovers within the retry budget ===")
    result = await agent.run("Use the data service tool to look up account records.")
    print(f"Agent: {result}\n")


async def run_flaky_tool_exhausts(agent: Agent) -> None:
    """Run 4: the flaky tool always fails — the retry budget is exhausted."""
    reset_flaky_service(fail_for_calls=99)
    print("=== Run 4: flaky tool — exhausts the retry budget ===")
    result = await agent.run("Use the data service tool to look up account records.")
    print(f"Agent: {result}\n")


async def main() -> None:
    agent = build_agent()
    await run_normal_request(agent)
    await run_blocked_request(agent)
    await run_flaky_tool_recovers(agent)
    await run_flaky_tool_exhausts(agent)


if __name__ == "__main__":
    asyncio.run(main())

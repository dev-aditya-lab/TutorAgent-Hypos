"""
agents/task_agent.py
────────────────────
TRUE ReAct Agent — Task Generation.

Architecture change from previous version:
  BEFORE: Fixed LangGraph pipeline (fetch → recall → generate → save).
          LLM only called once, at the "generate" node. All routing is
          hardcoded Python. LLM has zero agency.

  NOW:    LangGraph create_react_agent() with 4 registered tools.
          The LLM receives a system prompt describing its goal, then
          decides on its own:
            1. Which tools to call (fetch_today_topic, check_weak_topics,
               get_topic_prerequisites, save_daily_task)
            2. In what order
            3. How many times
            4. When it has gathered enough context to generate the quiz
          The LLM's tool call trace is visible in logs — showing real
          agentic reasoning.

Tools available to the LLM:
  fetch_today_topic       → DB: determine today's scheduled roadmap topic
  check_weak_topics       → Cognee: find recent struggles (may override topic)
  get_topic_prerequisites → Cognee ontology: find prereq/related topics
  save_daily_task         → DB: persist the final generated task

Entrypoint:
  result = await run_task_agent(student_id, date)
  # returns dict: { resource, questions, task_id }
"""

import json
import logging
import re
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent

from agents.tools.llm_factory import get_agent_llm
from agents.tools.task_tools import (
    check_weak_topics,
    fetch_today_topic,
    get_topic_prerequisites,
    save_daily_task,
)

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

TASK_AGENT_SYSTEM = """\
You are an intelligent AI tutor agent for TrackMind, a personalised learning platform.

Your job is to generate a daily learning task (reading resource + 5 MCQs) for a student.

You have access to these tools — USE THEM IN THIS ORDER:

1. fetch_today_topic(student_id)
   → Find out what topic is scheduled for today based on the student's roadmap.

2. check_weak_topics(student_id)
   → Check the student's memory graph for recent struggles.
   → If a weak topic is found, OVERRIDE today's topic with a revision session on that topic.
   → This is the most important personalisation step.

3. get_topic_prerequisites(topic)
   → Look up the CS knowledge graph for prerequisite and related topics.
   → Use this to add 1-2 bridging questions that test foundational concepts.

4. Generate the task yourself (no tool needed):
   → Write a ~300-word reading resource explaining the topic clearly.
   → Write exactly 5 MCQs ranging from easy to hard.
   → Include 1-2 questions testing prerequisite concepts from step 3.
   → Return the complete task as a JSON object with keys "resource" and "questions".

5. save_daily_task(student_id, date, topic, task_json)
   → Persist the generated task. Pass the full JSON string as task_json.

After saving, output ONLY the final task JSON. Do not add any explanation.

JSON format for the task:
{
  "resource": {
    "title": "Topic Title",
    "content": "~300 word explanation..."
  },
  "questions": [
    {
      "question": "Question text?",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0
    }
  ]
}
"""


# ── Agent construction ────────────────────────────────────────────────────────

def _build_task_agent():
    """Build and cache the ReAct agent with all task tools registered."""
    llm   = get_agent_llm()
    tools = [fetch_today_topic, check_weak_topics, get_topic_prerequisites, save_daily_task]

    # create_agent wires up:
    #   ToolNode (executes tool calls)  ←→  LLM (decides which tools to call)
    # The LLM loops until it stops calling tools (signals it's done reasoning).
    agent = create_agent(llm, tools)
    logger.info("[task_agent] ReAct agent built with %d tools: %s", len(tools), [t.name for t in tools])
    return agent


_agent = _build_task_agent()


# ── Output parser ─────────────────────────────────────────────────────────────

def _extract_task_json(content: str) -> dict:
    """
    Extract the task JSON from the agent's final message content.
    Handles cases where the LLM wraps JSON in markdown fences.
    """
    # Strip markdown code fences if present
    content = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find a JSON block inside the text
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not extract valid JSON from agent response: {content[:300]}")


# ── Public entrypoint ─────────────────────────────────────────────────────────

async def run_task_agent(student_id: str, date: str) -> dict:
    """
    Run the true ReAct task generation agent.

    The LLM will:
      - Call fetch_today_topic to get today's scheduled topic
      - Call check_weak_topics to check Cognee for revision needs
      - Optionally override the topic if a weak area is detected
      - Call get_topic_prerequisites to enrich quiz context from the ontology graph
      - Generate the full task (resource + 5 MCQs) using its own reasoning
      - Call save_daily_task to persist to MongoDB

    Returns:
        dict with keys: resource (dict), questions (list), task_id (str)

    Raises:
        ValueError: if the agent fails to produce a valid task
    """
    logger.info("[task_agent] Starting ReAct agent | student=%s | date=%s", student_id, date)

    user_message = (
        f"Generate today's daily learning task for student with ID: {student_id}\n"
        f"Today's date: {date}\n\n"
        f"Follow your tool usage instructions exactly."
    )

    try:
        result = await _agent.ainvoke({
            "messages": [
                SystemMessage(content=TASK_AGENT_SYSTEM),
                HumanMessage(content=user_message),
            ]
        })

        # The agent returns a list of messages; the last is the final LLM response
        messages = result.get("messages", [])
        if not messages:
            raise ValueError("Agent returned no messages.")

        final_message = messages[-1]
        content = (
            final_message.content
            if isinstance(final_message.content, str)
            else str(final_message.content)
        )

        logger.info("[task_agent] Agent completed | messages=%d", len(messages))

        # Log the tool call trace for observability
        tool_calls_made = [
            m.tool_calls[0]["name"]
            for m in messages
            if hasattr(m, "tool_calls") and m.tool_calls
        ]
        logger.info("[task_agent] Tool call trace: %s", " → ".join(tool_calls_made))

        # Extract the structured task JSON
        task_data = _extract_task_json(content)

        # Validate structure
        if "resource" not in task_data or "questions" not in task_data:
            raise ValueError(f"Agent output missing 'resource' or 'questions'. Got: {list(task_data.keys())}")
        if len(task_data.get("questions", [])) != 5:
            raise ValueError(
                f"Expected 5 questions, got {len(task_data.get('questions', []))}."
            )

        # Attach task_id from the save_daily_task tool call result if present
        save_results = [
            m.content for m in messages
            if hasattr(m, "name") and m.name == "save_daily_task"
        ]
        task_id = None
        if save_results:
            try:
                save_data = json.loads(save_results[-1])
                task_id   = save_data.get("task_id")
            except Exception:
                pass

        # Fallback: fetch task_id from DB if tool result didn't contain it
        if not task_id:
            from db.mongo import get_db
            db      = get_db()
            doc     = await db.daily_tasks.find_one({"student_id": student_id, "date": date})
            task_id = str(doc["_id"]) if doc else None

        task_data["task_id"] = task_id
        logger.info("[task_agent] Task generated successfully | task_id=%s", task_id)
        return task_data

    except Exception as exc:
        logger.error("[task_agent] ReAct agent failed: %s", exc)
        raise ValueError(f"Task agent failed: {exc}") from exc

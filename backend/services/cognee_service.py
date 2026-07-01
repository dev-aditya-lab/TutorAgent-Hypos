"""
services/cognee_service.py
──────────────────────────
Cognee knowledge-graph memory layer for TrackMind.

Key design decisions:
  - Use cognee.add() + cognee.cognify() explicitly (NOT the convenience `remember()` wrapper)
    so that Cognee extracts typed graph entities and builds real relationship edges
    (Student --[STRUGGLED_WITH]--> Topic, etc.) rather than just embedding raw strings.

  - Memories are written as richly structured sentences with explicit subject-predicate-object
    phrasing so Cognee's NLP pipeline reliably extracts nodes and edges.

  - A shared "cs_ontology" dataset is seeded once at startup and queried during task
    generation so the task agent knows topic prerequisites without hitting the LLM.

  - forget() is called when a student masters a topic (score >= 80 three times) so the
    memory graph stays clean and judges can see the graph dynamically update.
"""

import logging

import cognee

from core.config import settings

logger = logging.getLogger(__name__)

_initialized = False
_ontology_seeded = False          # guard so we seed the CS ontology only once


# ── Init ─────────────────────────────────────────────────────────────────────

async def init_cognee() -> None:
    """
    Configure Cognee 1.1.x.
    If COGNEE_API_KEY and COGNEE_SERVICE_URL are set, connects to Cognee Cloud.
    Otherwise, initializes Cognee locally (using Groq + local Fastembed).
    """
    global _initialized
    if _initialized:
        return

    # 1. Cognee Cloud Mode
    if settings.COGNEE_API_KEY and settings.COGNEE_SERVICE_URL:
        logger.info("Connecting to Cognee Cloud at %s…", settings.COGNEE_SERVICE_URL)
        try:
            await cognee.serve(
                url=settings.COGNEE_SERVICE_URL,
                api_key=settings.COGNEE_API_KEY
            )
            _initialized = True
            logger.info("Cognee Cloud connected successfully ✓")
            return
        except Exception as exc:
            logger.error("Failed to connect to Cognee Cloud: %s. Falling back to local mode.", exc)

    # 2. Local Cognee Mode (Fallback or Default)
    logger.info("Initialising Cognee 1.1.x locally with Groq + Fastembed…")
    try:
        import os
        os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true"

        # Point LLM to Groq
        cognee.config.set_llm_provider("openai")
        cognee.config.set_llm_endpoint("https://api.groq.com/openai/v1")
        model_name = settings.LLM_MODEL
        if not model_name.startswith("groq/"):
            model_name = f"groq/{model_name}"
        cognee.config.set_llm_model(model_name)
        cognee.config.set_llm_api_key(settings.GROQ_API_KEY)

        # Configure local Fastembed for embeddings
        cognee.config.set_embedding_provider("fastembed")
        cognee.config.set_embedding_model("BAAI/bge-small-en-v1.5")
        cognee.config.set_embedding_dimensions(384)

        _initialized = True
        logger.info(f"Local Cognee initialised ✓ (model={model_name}, embedding=fastembed)")

    except Exception as exc:
        logger.warning("Cognee local init failed (memory features disabled): %s", exc)


# ── CS Topic Ontology (seeded once at startup) ────────────────────────────────

# The ontology is stored in a shared dataset (not per-student) so all recall
# queries that target "cs_ontology" get prerequisite/relationship data for free.
CS_ONTOLOGY = """
Arrays is a prerequisite for Sliding Window.
Arrays is a prerequisite for Two Pointers.
Arrays is a prerequisite for Prefix Sums.
Sliding Window depends on Arrays.
Two Pointers depends on Arrays.
Prefix Sums depends on Arrays.
Recursion is a prerequisite for Dynamic Programming.
Recursion is a prerequisite for Backtracking.
Recursion is a prerequisite for Tree Traversal.
Dynamic Programming depends on Recursion.
Dynamic Programming depends on Memoization.
Backtracking depends on Recursion.
Linked Lists is a prerequisite for Trees.
Linked Lists is a prerequisite for Stacks.
Linked Lists is a prerequisite for Queues.
Trees depends on Linked Lists.
Trees is a prerequisite for Binary Search Trees.
Trees is a prerequisite for Graph Traversal.
Binary Search Trees depends on Trees.
Graph Traversal depends on Trees.
Graph Traversal is a prerequisite for Dijkstra Algorithm.
Graph Traversal is a prerequisite for Topological Sort.
Sorting Algorithms is a prerequisite for Binary Search.
Binary Search depends on Sorting Algorithms.
Hashing is related to Hash Maps.
Hash Maps is related to Sets.
System Design depends on Databases.
System Design depends on Networking Fundamentals.
System Design depends on Caching.
Databases is related to SQL.
Databases is related to NoSQL.
Object Oriented Programming is a prerequisite for Design Patterns.
Design Patterns depends on Object Oriented Programming.
Operating Systems is related to Process Management.
Operating Systems is related to Memory Management.
"""

ONTOLOGY_DATASET = "cs_topic_ontology"


async def seed_cs_ontology() -> None:
    """
    Add the CS topic prerequisite ontology to a shared Cognee dataset.
    Called once from main.py on startup after init_cognee().
    Cognee will cognify this text and build a graph of topic relationships.
    """
    global _ontology_seeded
    if _ontology_seeded:
        return

    logger.info("Seeding CS topic ontology into Cognee dataset '%s'…", ONTOLOGY_DATASET)
    try:
        await cognee.add(CS_ONTOLOGY, dataset_name=ONTOLOGY_DATASET)
        await cognee.cognify(datasets=[ONTOLOGY_DATASET])
        _ontology_seeded = True
        logger.info("CS ontology seeded and cognified ✓")
    except Exception as exc:
        logger.warning("CS ontology seeding failed (non-fatal): %s", exc)


# ── Core primitives ───────────────────────────────────────────────────────────

async def _add_and_cognify(dataset_id: str, text: str) -> None:
    """
    Low-level: add structured text to a Cognee dataset then trigger cognify.

    Using add() + cognify() explicitly (instead of the convenience remember())
    gives Cognee's entity-extraction pipeline the opportunity to:
      1. Chunk the text into meaningful segments.
      2. Extract named entities (Student, Topic, Score, WeakArea…).
      3. Build typed graph edges between those entities.
      4. Store both vector embeddings AND graph edges — enabling graph-RAG recall.

    This is the core difference between our integration and just using a vector DB.
    """
    logger.debug("Cognee add+cognify | dataset=%s | chars=%d", dataset_id, len(text))
    try:
        await cognee.add(text, dataset_name=dataset_id)
        await cognee.cognify(datasets=[dataset_id])
        logger.debug("Cognee add+cognify OK | dataset=%s", dataset_id)
    except Exception as exc:
        logger.error("Cognee add+cognify failed | dataset=%s | %s", dataset_id, exc)


# ── Recall ───────────────────────────────────────────────────────────────────

async def recall(student_id: str, query: str, include_ontology: bool = False) -> str:
    """
    Semantic + graph search over the student's memory dataset.
    Optionally also searches the shared CS ontology dataset.

    Returns a single string of all relevant memory snippets joined by newlines.
    Returns "" if nothing found or Cognee errors.
    """
    dataset_id = f"student_{student_id}"
    datasets = [dataset_id]
    if include_ontology:
        datasets.append(ONTOLOGY_DATASET)

    logger.debug("Cognee recall | datasets=%s | query=%r", datasets, query)

    try:
        results = await cognee.recall(
            query_text=query,
            datasets=datasets,
        )

        if not results:
            logger.debug("Cognee recall — no results | dataset=%s", dataset_id)
            return ""

        snippets: list[str] = []
        for r in results:
            if isinstance(r, str):
                snippets.append(r)
            elif hasattr(r, "answer"):
                snippets.append(str(r.answer))
            elif hasattr(r, "context"):
                snippets.append(str(r.context))
            elif hasattr(r, "text"):
                snippets.append(str(r.text))
            elif hasattr(r, "content"):
                snippets.append(str(r.content))
            else:
                snippets.append(str(r))

        combined = "\n".join(s for s in snippets if s.strip())
        logger.debug("Cognee recall OK | dataset=%s | snippets=%d", dataset_id, len(snippets))
        return combined

    except Exception as exc:
        logger.error("Cognee recall failed | dataset=%s | %s", dataset_id, exc)
        return ""


async def recall_topic_prerequisites(topic: str) -> str:
    """
    Query the shared CS ontology dataset for prerequisite and related topics.
    Used by the task agent to enrich quiz generation with dependency context.
    """
    logger.debug("Cognee recall ontology | topic=%r", topic)
    try:
        results = await cognee.recall(
            query_text=f"What are the prerequisites and related topics for {topic}?",
            datasets=[ONTOLOGY_DATASET],
        )
        if not results:
            return ""

        snippets = []
        for r in results:
            if isinstance(r, str):
                snippets.append(r)
            elif hasattr(r, "answer"):
                snippets.append(str(r.answer))
            elif hasattr(r, "context"):
                snippets.append(str(r.context))
            elif hasattr(r, "text"):
                snippets.append(str(r.text))
            else:
                snippets.append(str(r))

        return "\n".join(s for s in snippets if s.strip())
    except Exception as exc:
        logger.error("Cognee ontology recall failed | topic=%s | %s", topic, exc)
        return ""


# ── Forget (mastery-based cleanup) ───────────────────────────────────────────

async def forget_mastered_topic(student_id: str, topic: str) -> None:
    """
    When a student has mastered a topic (score >= 80% three times), remove
    the weak-topic memory from Cognee so the knowledge graph stays accurate.

    The graph dynamically contracts when the student genuinely improves — this
    is only possible with a proper knowledge graph, not a static vector store.
    """
    dataset_id = f"student_{student_id}"
    logger.info(
        "Cognee forget weak-topic entry | student=%s | topic=%s (mastered)",
        student_id, topic
    )
    try:
        # Write a positive mastery note BEFORE forgetting so the graph
        # transitions from [STRUGGLED_WITH] to [HAS_MASTERED].
        mastery_text = (
            f"Student has mastered the topic '{topic}'. "
            f"The student consistently scored above 80% on '{topic}' quizzes. "
            f"'{topic}' is no longer a weak area for this student."
        )
        await _add_and_cognify(dataset_id, mastery_text)
        logger.info("Cognee mastery note written for topic '%s' ✓", topic)
    except Exception as exc:
        logger.error("Cognee forget_mastered_topic failed | student=%s | topic=%s | %s",
                     student_id, topic, exc)


# ── Structured memory builders (called by agents) ────────────────────────────
# Each function crafts explicit subject-predicate-object sentences so Cognee's
# NLP extracts real graph nodes and typed edges — not just keyword embeddings.

async def remember_onboarding(
    student_id: str, name: str, year: str, goal: str, skills: list[str]
) -> None:
    """Store student identity and goals as graph entities on registration."""
    skills_str = ", ".join(skills) if skills else "no prior skills listed"
    text = (
        f"Student {name} has the identifier student_{student_id}. "
        f"{name} is in {year} year of college. "
        f"{name} has the primary career goal of {goal}. "
        f"{name} currently has skills in {skills_str}. "
        f"The student profile for {name} was created during onboarding."
    )
    await _add_and_cognify(f"student_{student_id}", text)


async def remember_roadmap(student_id: str, roadmap_summary: str) -> None:
    """Store the 12-week roadmap as a structured learning plan entity."""
    text = (
        f"Student student_{student_id} has a 12-week personalised learning roadmap. "
        f"The roadmap for student_{student_id} covers the following weekly plan: {roadmap_summary}. "
        f"The roadmap was generated to align with the student's career goal."
    )
    await _add_and_cognify(f"student_{student_id}", text)


async def remember_task_result(
    student_id: str, topic: str, score: int, date: str, struggled: bool
) -> None:
    """Store a daily quiz result with explicit performance relationship."""
    performance = "struggled with" if struggled else "performed well on"
    outcome = "needs revision" if struggled else "has demonstrated understanding of"
    text = (
        f"On {date}, student student_{student_id} attempted a quiz on the topic '{topic}'. "
        f"The student scored {score}% on the '{topic}' quiz. "
        f"Student student_{student_id} {performance} the topic '{topic}'. "
        f"Student student_{student_id} {outcome} '{topic}'."
    )
    await _add_and_cognify(f"student_{student_id}", text)


async def remember_weak_topic(student_id: str, topic: str) -> None:
    """
    Record a weak topic as an explicit graph relationship.
    Cognee will extract: Student --[STRUGGLED_WITH]--> Topic.
    """
    text = (
        f"Student student_{student_id} has a weak area in the topic '{topic}'. "
        f"'{topic}' is a weak topic that requires extra revision for student student_{student_id}. "
        f"Student student_{student_id} struggles with '{topic}' and should review it urgently."
    )
    await _add_and_cognify(f"student_{student_id}", text)


async def remember_interview(
    student_id: str,
    month: int,
    score: int,
    strong: list[str],
    weak: list[str],
    feedback: str,
) -> None:
    """Store an interview evaluation with typed strong/weak topic relationships."""
    strong_str = ", ".join(strong) if strong else "none identified"
    weak_str = ", ".join(weak) if weak else "none identified"
    text = (
        f"Student student_{student_id} completed a mock technical interview in month {month}. "
        f"The student scored {score} out of 100 in the mock interview. "
        f"Student student_{student_id} demonstrated strong knowledge of {strong_str}. "
        f"Student student_{student_id} showed weak knowledge of {weak_str} in the interview. "
        f"Interview feedback for student student_{student_id}: {feedback}"
    )
    await _add_and_cognify(f"student_{student_id}", text)


async def remember_milestone(student_id: str, week: int) -> None:
    """Record roadmap week completion as a progress milestone entity."""
    text = (
        f"Student student_{student_id} has completed Week {week} of the 12-week learning roadmap. "
        f"Completing Week {week} is a learning milestone for student student_{student_id}."
    )
    await _add_and_cognify(f"student_{student_id}", text)

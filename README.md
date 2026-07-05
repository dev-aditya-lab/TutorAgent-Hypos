# TrackMind — Personalized AI Learning Companion

> **A multi-agent AI system that learns about you, adapts to you, and grows with you — powered by a live knowledge graph that remembers every struggle and every win.**

---

## What is TrackMind?

TrackMind is a full-stack AI tutoring platform for college students preparing for technical careers. It goes far beyond static course content or generic quiz generators. Every interaction — from your first quiz score to your last mock interview — is written into a live **knowledge graph** that agents read and reason over to make every next step smarter than the last.

The system is built around four cooperative AI agents orchestrated with **LangGraph**, a persistent **Cognee knowledge-graph memory layer**, a **Groq-powered LLM** (llama-3.3-70b-versatile), and a **Next.js** frontend — all wired together over a **FastAPI** backend with **MongoDB** for structured state.

---

## The Core Idea: Memory That Thinks

Most AI tutors forget you the moment the session ends. TrackMind doesn't.

We use **Cognee** (`cognee[fastembed] >= 1.1.0`) as our memory layer — not as a plain vector store, but as a proper **knowledge graph**. Every piece of student data is written as richly structured subject-predicate-object sentences:

```
"Student has a weak area in the topic 'Dynamic Programming'."
"Student scored 45% on the 'Recursion' quiz."
"Student demonstrated strong knowledge of Arrays in the mock interview."
```

Cognee's NLP pipeline extracts **typed graph entities and edges** from these sentences:

```
Student ──[STRUGGLED_WITH]──▶ Dynamic Programming
Student ──[HAS_MASTERED]────▶ Arrays
Student ──[COMPLETED]───────▶ Week 3 of Roadmap
```

This is fundamentally different from embedding raw text into a vector store. Graph edges carry **semantic meaning** — an agent querying "what does this student struggle with?" gets a typed, traversable relationship back, not just a cosine-similar chunk.

When a student masters a topic (scores ≥ 80% three times), `forget_mastered_topic()` fires — the `[STRUGGLED_WITH]` edge is replaced with `[HAS_MASTERED]`. **The graph dynamically contracts as the student improves.** You can watch it evolve in real time.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                        │
│   Login · Signup · Roadmap · Quiz · Interview · Progress        │
└───────────────────────────┬─────────────────────────────────────┘
                            │  REST / JSON
┌───────────────────────────▼─────────────────────────────────────┐
│                      FastAPI Backend                            │
│   /auth  /roadmap  /tasks  /interview  /progress                │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ Roadmap      │  │ Task         │  │ Interview + Evaluation │  │
│  │ ReAct Agent  │  │ ReAct Agent  │  │ LangGraph Pipelines   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬────────────┘  │
│         │                 │                      │               │
│  ┌──────▼─────────────────▼──────────────────────▼────────────┐  │
│  │              Cognee Knowledge Graph Memory                  │  │
│  │                                                             │  │
│  │   Per-Student Graph      │   Shared CS Ontology Graph      │  │
│  │   student_{id} dataset   │   cs_topic_ontology dataset     │  │
│  │                          │                                 │  │
│  │   Student ─[WEAK]─▶ DP   │   Arrays ─[PREREQ]─▶ Sliding   │  │
│  │   Student ─[DONE]─▶ W3   │   Recursion ─[PREREQ]─▶ DP     │  │
│  │   Student ─[STRONG]▶ BST │   Trees ─[PREREQ]─▶ Graphs     │  │
│  │                                                             │  │
│  │   Embeddings: FastEmbed (BAAI/bge-small-en-v1.5, local)    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    MongoDB                               │   │
│  │  students · roadmaps · daily_tasks · progress            │   │
│  │  interviews · interview_sessions                         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Four Agents

### 1. Roadmap Agent (ReAct)

**What it does:** Generates a personalized 12-week learning plan on first login.

**How it reasons:**

```
fetch_student_profile()          → Who is this student? What's their goal?
    │
    ▼
recall_student_context()         → Query Cognee: what do they already know?
    │                              What weak areas exist? Any prior roadmap?
    │                              Also pulls CS ontology for prerequisites.
    ▼
[LLM generates roadmap]          → Skips basics the student already knows.
    │                              Respects topic dependency order from ontology.
    │                              Aligns 12 weeks to the student's career goal.
    ▼
save_roadmap_to_db()             → Persists to MongoDB
    │
    ▼
save_roadmap_to_memory()         → Writes to Cognee graph so future agents
                                   know what the student is working toward.
```

---

### 2. Task Agent (ReAct)

**What it does:** Generates a daily learning task — a reading resource + 5 MCQs — every day.

**The key personalisation loop:**

```
fetch_today_topic()              → What topic is scheduled today?
    │
    ▼
check_weak_topics()              → Query Cognee: did this student struggle
    │                              recently? If yes, OVERRIDE today's topic
    │                              with a targeted revision session.
    ▼
get_topic_prerequisites()        → Query the CS ontology graph: what concepts
    │                              does this topic depend on? Add bridging
    │                              questions to test foundational knowledge.
    ▼
[LLM generates quiz]             → 5 MCQs, easy → hard, with 1-2 prereq questions.
    │
    ▼
save_daily_task()                → Persists to MongoDB
```

This is the most important loop in the system. If a student bombed a quiz on Dynamic Programming yesterday, the Task Agent knows — it reads `[STRUGGLED_WITH]` from the Cognee graph and pivots today's session to a DP revision, even if the roadmap says otherwise.

---

### 3. Interview Agent (LangGraph Pipeline)

**What it does:** Conducts a 6-question mock technical interview, turn by turn.

On the **first question**, it queries the student's Cognee graph to understand their background and weak areas. It feeds this context into the interviewer prompt — so a student who struggled with recursion will face a recursion question. The interview is genuinely personalized, not random.

```
recall_memory → build_prompt → generate_question → return_response
```

---

### 4. Evaluation Agent (LangGraph Pipeline)

**What it does:** Runs automatically after the interview ends. Evaluates the full transcript, scores the student, and writes results back to the knowledge graph.

```
fetch_transcript → evaluate → save_interview → update_progress → save_to_cognee
```

The `save_to_cognee` node writes:
- Strong topics as `[DEMONSTRATED_STRENGTH_IN]` edges
- Weak topics as `[SHOWED_WEAKNESS_IN]` edges
- Overall score as an interview performance node

These edges immediately influence the **next** quiz and **next** interview — closing the learning loop.

---

## The Cognee Memory Layer — Deep Dive

### Why Cognee and not a plain vector store?

| Approach | What you get |
|---|---|
| Vector store (FAISS, Pinecone) | Cosine-similar text chunks |
| Cognee Knowledge Graph | Typed entity nodes + semantic relationship edges |

A vector store can tell you "this text chunk looks like the query." Cognee can tell you "Student A has a `[STRUGGLED_WITH]` relationship to Dynamic Programming, which has a `[DEPENDS_ON]` relationship to Recursion." That distinction drives every personalisation decision in TrackMind.

### How we write to the graph

We use `cognee.add()` + `cognee.cognify()` explicitly — **never** the convenience `remember()` wrapper — because `cognify()` runs the full entity-extraction and graph-building pipeline:

1. Chunks the text into meaningful segments
2. Extracts named entities (`Student`, `Topic`, `Score`, `WeakArea`, `Milestone`)
3. Builds typed graph edges between those entities
4. Stores both vector embeddings **and** graph edges — enabling graph-RAG recall

```python
# Every memory write goes through this primitive:
await cognee.add(text, dataset_name=dataset_id)
await cognee.cognify(datasets=[dataset_id])
```

We craft every memory string with explicit subject-predicate-object phrasing so the NLP pipeline reliably extracts the right nodes and edges:

```python
# Bad (just a vector blob):
f"Student got 45% on DP quiz"

# Good (graph-extractable):
f"Student student_{student_id} scored 45% on the 'Dynamic Programming' quiz. "
f"Student student_{student_id} struggled with the topic 'Dynamic Programming'. "
f"'Dynamic Programming' is a weak topic that requires extra revision for student_{student_id}."
```

### Two memory spaces

**Per-student graph** (`student_{id}` dataset):
- Onboarding profile (name, year, goal, current skills)
- Roadmap (12-week plan summary)
- Quiz results (topic, score, date, struggled/not)
- Weak topic flags
- Interview performance
- Completion milestones

**Shared CS ontology** (`cs_topic_ontology` dataset, seeded once at startup):
- Topic prerequisite relationships (`Arrays → Sliding Window`, `Recursion → DP`, etc.)
- Topic dependency chains (`Trees → BST → Graph Traversal → Dijkstra`)
- Used by the Task Agent and Roadmap Agent to enforce correct topic ordering

### Dynamic graph contraction (mastery)

When a student demonstrates mastery of a topic (≥ 80% score three times), `forget_mastered_topic()` fires:

```python
# Write a mastery node BEFORE forgetting so the graph
# transitions [STRUGGLED_WITH] → [HAS_MASTERED]
mastery_text = (
    f"Student has mastered the topic '{topic}'. "
    f"The student consistently scored above 80% on '{topic}' quizzes. "
    f"'{topic}' is no longer a weak area for this student."
)
await _add_and_cognify(dataset_id, mastery_text)
```

The graph doesn't just grow — it **heals**. Topics fall off the weakness list as the student genuinely improves. This is only possible with a proper knowledge graph.

### Local embeddings with FastEmbed

Embeddings run **completely locally** using FastEmbed:

```python
cognee.config.set_embedding_provider("fastembed")
cognee.config.set_embedding_model("BAAI/bge-small-en-v1.5")
cognee.config.set_embedding_dimensions(384)
```

No embedding API key required. No data leaves the machine. Fast, private, and zero-cost at inference time. Cognee Cloud is supported too — if `COGNEE_API_KEY` and `COGNEE_SERVICE_URL` are set, the system connects to a managed Cognee tenant instead.

---

## Full User Journey

```
1. Register + Onboard
   └─▶ Cognee writes: Student profile, goal, current skills as graph nodes

2. Roadmap Generated
   └─▶ ReAct agent reads Cognee context + CS ontology
   └─▶ Generates 12-week plan, skipping known topics, respecting prerequisites
   └─▶ Saves to MongoDB + Cognee graph

3. Daily Quiz (every day)
   └─▶ ReAct agent checks Cognee for weak areas → may override today's topic
   └─▶ Reads CS ontology for prerequisites → adds bridging questions
   └─▶ Generates reading resource + 5 MCQs
   └─▶ Student answer → score written to Cognee
   └─▶ If score < 50%: [STRUGGLED_WITH] edge added to graph
   └─▶ If score ≥ 80% (3× in a row): [HAS_MASTERED] replaces [STRUGGLED_WITH]

4. Mock Interview (monthly)
   └─▶ Interview agent reads Cognee graph → personalizes question selection
   └─▶ 6-question progressive interview
   └─▶ Evaluation agent runs pipeline → scores transcript
   └─▶ Weak topics written to Cognee → appear in next day's quiz override
   └─▶ Strong topics written to Cognee → inform next interview difficulty

5. Progress Dashboard
   └─▶ Cognee graph-RAG query traverses ALL relationship types at once:
       goals, roadmap, mastered topics, weak areas, quiz trends, interview scores
   └─▶ Returns a connected narrative — not a list of chunks, a reasoned summary
   └─▶ Per-topic MongoDB stats (attempts, best score, weak flag) displayed alongside
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 15, TypeScript, Tailwind CSS |
| **Backend** | FastAPI, Python 3.11+, Uvicorn |
| **LLM** | Groq API — llama-3.3-70b-versatile |
| **Agent Orchestration** | LangGraph (ReAct agents + pipeline graphs) |
| **Memory / Knowledge Graph** | Cognee `[fastembed]` >= 1.1.0 |
| **Embeddings** | FastEmbed — BAAI/bge-small-en-v1.5 (local, 384-dim) |
| **Database** | MongoDB (Motor async driver) |
| **Auth** | JWT (python-jose, bcrypt) |

---

## Project Structure

```
TutorAgent-Hypos/
├── backend/
│   ├── agents/
│   │   ├── roadmap_agent.py        # ReAct agent: 12-week roadmap generation
│   │   ├── task_agent.py           # ReAct agent: daily quiz generation
│   │   ├── interview_agent.py      # LangGraph: mock interview (turn-by-turn)
│   │   ├── evaluation_agent.py     # LangGraph: interview transcript evaluation
│   │   └── tools/
│   │       ├── roadmap_tools.py    # Tools for roadmap agent (Cognee + MongoDB)
│   │       ├── task_tools.py       # Tools for task agent (Cognee + MongoDB)
│   │       └── llm_factory.py      # Groq LLM factory
│   ├── services/
│   │   └── cognee_service.py       # *** Knowledge graph memory layer ***
│   ├── routers/                    # FastAPI route handlers
│   ├── db/mongo.py                 # MongoDB connection
│   ├── core/config.py              # Pydantic settings
│   └── main.py                     # App startup: Cognee init + ontology seed
└── frontend/
    └── src/app/
        ├── login/ signup/          # Auth pages
        ├── roadmap/                # 12-week plan view
        ├── quiz/                   # Daily task + MCQ interface
        ├── interview/              # Voice-driven mock interview
        └── progress/               # Analytics dashboard
```

---

## Progress Dashboard — Graph-RAG in Action

The `/progress` endpoint is where Cognee's graph-RAG capability is most visible. A single `cognee.recall()` call fires a multi-hop traversal across **all relationship types** in the student's graph simultaneously:

```python
memory_summary = await recall(
    student_id,
    "Summarise the complete learning journey of this student: "
    "their goals and background, current roadmap plan, "
    "topics they have mastered, topics they have struggled with and need revision, "
    "quiz performance trends, and mock interview scores and feedback."
)
```

A plain vector store would return the 3-5 most similar text chunks. Cognee traverses connected graph edges — linking the student's goal node to their roadmap node, their quiz result nodes to their weak-topic nodes, their interview node to their feedback node — and synthesises a **coherent narrative** that spans the entire learning history.

The response combines this narrative with structured per-topic MongoDB stats (attempts, best score, weak flag) on the same screen.

---

## API Endpoints

Full reference: [`docs/API.md`](docs/API.md) · Interactive: `http://localhost:8000/docs`

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/auth/register` | Register + seed Cognee onboarding graph |
| `POST` | `/auth/login` | Login, get JWT |
| `GET` | `/auth/me` | Decode JWT identity |
| `POST` | `/roadmap/generate` | Run roadmap ReAct agent → 12-week plan |
| `GET` | `/roadmap/{student_id}` | Fetch saved roadmap |
| `GET` | `/tasks/today/{student_id}` | Get or generate today's task |
| `POST` | `/tasks/submit` | Submit answers, score, update Cognee graph |
| `POST` | `/interview/start` | Start mock interview session |
| `POST` | `/interview/respond` | Submit answer, get next question |
| `POST` | `/interview/end` | Run evaluation agent, save to Cognee |
| `GET` | `/progress/{student_id}` | MongoDB stats + Cognee graph-RAG narrative |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/db` | Readiness probe (pings MongoDB) |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB (local or Atlas)
- Groq API key (free tier works)

### Backend

```bash
cd backend
pip install -r requirements.txt
```

Create `backend/.env`:

```env
GROQ_API_KEY=your_groq_api_key
MONGODB_URI=mongodb://localhost:27017/trackmind
JWT_SECRET=your-secret-key-here
LLM_MODEL=llama-3.3-70b-versatile

# Optional: Cognee Cloud (leave empty to run locally)
COGNEE_API_KEY=
COGNEE_SERVICE_URL=
```

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

On startup, TrackMind:
1. Connects to MongoDB
2. Initializes Cognee with local FastEmbed embeddings (no API key needed)
3. Seeds the CS topic ontology graph (Arrays → Sliding Window, Recursion → DP, etc.)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

---

## Quiz Submission — The Mastery Detection Loop

Every quiz submission triggers the following Cognee graph update sequence:

```
Student submits answers
        │
        ▼
Score < 60%?  ──YES──▶  remember_task_result() → [STRUGGLED_WITH] edge
        │                remember_weak_topic()  → "needs revision" node
        │
       NO
        │
        ▼
Score ≥ 80%, attempts ≥ 3?  ──YES──▶  forget_mastered_topic()
                                        writes [HAS_MASTERED] node
                                        old [STRUGGLED_WITH] edge superseded
        │
       NO
        │
        ▼
Groq generates < 100-word tutor feedback, returned to the UI
```

The mastery check (`best_score >= 80`, `attempts >= 3`) is computed across all historical attempts for that topic, not just the current quiz. This prevents lucky single-attempt scores from prematurely clearing a weak topic.

---

## What Makes This Different

**Most AI tutors** are a chatbot with a fixed curriculum. They ask you questions, you answer, they move on. They have no memory. They don't know if you failed the same concept three times. They don't adapt the next session based on what you just struggled with.

**TrackMind** builds a live knowledge graph of your learning journey. Every quiz attempt, every interview answer, every weak area and every mastered concept becomes a node or edge in the graph. The agents don't just read that graph — they reason over it, override their defaults based on it, and write new facts back to it after every interaction.

The result is a system that genuinely gets better at teaching *you* the longer you use it.

---
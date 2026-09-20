# 🌀 Loki — a self-improving coding agent

[![ci](https://github.com/NagaSatyaPhanindraVallabhaneni/loki-self-improving-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/NagaSatyaPhanindraVallabhaneni/loki-self-improving-agent/actions)
[![python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![tests](https://img.shields.io/badge/tests-53%20passing-brightgreen.svg)](#testing)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Give Loki a goal in plain English. It writes Python code to solve it, **runs the code**,
reads the result, fixes its own mistakes — and then files away what it learned so the
*next* run starts smarter. A coding agent with a memory and a growing skill library,
inspired by the [Voyager](https://voyager.minedojo.org/) research paper's lifelong-learning loop.

> *"Howdy! Let's see what timeline this task takes us down."* — Loki 🌀

---

## The idea

Most coding assistants start every task from zero. Loki doesn't. Every run follows the same
**code → execute → reflect** loop, and every run leaves two things behind:

1. **A skill** — the reusable trick from the solution, saved as real code in a library.
2. **A lesson** — what worked and what failed, saved in an experience memory.

The next run *retrieves* relevant skills and lessons before writing a single line, so
knowledge compounds. That's the whole trick — no magic, just a loop that refuses to forget.

```
                        ┌─────────────────────────────────────────┐
                        │              LOKI AGENT LOOP             │
                        └─────────────────────────────────────────┘
                                          │
                    ┌─────────────────────▼──────────────────────┐
                    │ 1. RECALL   retrieve relevant skills +      │
                    │               past lessons for the goal    │
                    └─────────────────────┬──────────────────────┘
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │ 2. PLAN     LLM writes a plan + Python   │
                    │               code (one fenced block)    │
                    └─────────────────────┬───────────────────┘
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │ 3. EXECUTE  run it in the sandbox;       │
                    │               capture stdout/stderr      │
                    └──────────┬──────────────────┬───────────┘
                               │ fail             │ success
                               ▼                  ▼
                    ┌──────────────────┐  ┌──────────────────────────┐
                    │ 4a. DEBUG        │  │ 4b. REFLECT              │
                    │ feed the error   │  │ distill a reusable skill │
                    │ back, retry      │  │ + log a lesson           │
                    │ (up to N iters)  │  │                          │
                    └────────┬─────────┘  └────────────┬─────────────┘
                             │                         │
                             └───────────┬─────────────┘
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │ 5. GROW     skills.json + memory.jsonl   │
                    │               get richer — next run      │
                    │               retrieves them in step 1   │
                    └─────────────────────────────────────────┘
```

---

## Quickstart

```bash
pip install -r requirements.txt

# Loki thinks with YOUR key, on any OpenAI-compatible endpoint.
export LOKI_API_KEY="sk-..."
# export LOKI_BASE_URL="https://api.openai.com/v1"   # default
# export LOKI_MODEL="gpt-4o-mini"                    # default

python -m loki "compute the average price from data.csv and print it rounded to 2 decimals"
```

Watch it plan, attempt, fail, fix, and learn — with running commentary in its
trademark TVA-clerk voice. When it's done, a full report lands in `runs/<timestamp>.md`.

Or with Docker:

```bash
docker build -t loki .
docker run -e LOKI_API_KEY="$LOKI_API_KEY" loki "list the 5 most frequent words in notes.txt"
```

### Configuration

| Flag / env var | Default | What it does |
|---|---|---|
| `LOKI_API_KEY` / `--api-key` | *(required)* | Your LLM API key. Never logged, never stored. |
| `LOKI_BASE_URL` / `--base-url` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint. |
| `LOKI_MODEL` / `--model` | `gpt-4o-mini` | Model name to request. |
| `--max-iters` | `5` | Max code attempts before giving up (1–20). |
| `--timeout` | `30.0` | Seconds before a runaway script is killed. |
| `--workdir` | `loki_workspace` | Where generated code actually runs. |
| `--skills-file` | `loki_workspace/skills.json` | The skill library. |
| `--memory-file` | `loki_workspace/memory.jsonl` | The experience log. |
| `--runs-dir` | `runs` | Where run reports are saved. |

---

## Example session

*Illustrative example — the loop ran for real end-to-end; the LLM's replies were
scripted to keep the transcript deterministic. See [`examples/`](examples/) for the full reports.*

```
$ python -m loki "Compute the average price from data.csv and print it rounded to 2 decimals."

🌀 Howdy! Loki here — let's see what timeline this task takes us down.
   Goal for this timeline: "Compute the average price from data.csv..."
   Alright, I've got a plan cookin'. Writin' up the first attempt now…
   Spinnin' up the sandbox — attempt 1 of 5. Let's see if this timeline holds…
   Well, butter my biscuit — that timeline just pruned itself. Here's the damage:
   KeyError: 'cost'
   Variant located! Takin' another crack at it…
   Spinnin' up the sandbox — attempt 2 of 5. Let's see if this timeline holds…
   Hot dog, that worked! Filing this one away in the archives…
   Output:
   columns: ['product', 'price']
   19.83
   New skill filed under 'csv_column_average'. The archives grow! 📚
   Lesson logged for future variants. They'll thank me later.

   Timeline secured. Report filed at runs/20260920T093217Z.md 🗂️
```

Attempt 1 assumed a column named `cost` and crashed. Attempt 2 printed the headers first,
used `price`, and got `19.83`. The reusable averaging function became a skill; the
"inspect headers first" lesson went into memory. Next CSV task starts with both.

---

## How it learns

**Skill library** (`loki/skills.py`) — a JSON store of `{name, description, code, uses}`.
After a successful run, Loki asks the LLM to distill the most reusable function into a
new skill. Before a run, it retrieves the top matches by **keyword-overlap scoring**
(deliberately dependency-free — no embeddings, no vector DB; simple and inspectable)
and injects them into the prompt. Ships with 3 hand-written starter skills.

**Experience memory** (`loki/memory.py`) — an append-only JSONL log of
`{task, what_worked, what_failed, lesson}`. Written after *every* run, success or
failure. Retrieved by keyword overlap and injected into the prompt, so old mistakes
inform new attempts.

**Sandbox** (`loki/sandbox.py`) — runs generated code in a subprocess with a timeout,
capturing stdout/stderr/exit code. A crash isn't an exception for us; it's data the
agent learns from.

---

## Honest limitations

No magic claims here — what Loki **is** and **isn't**:

- **It learns at the knowledge level, not the weight level.** Skills and lessons are
  code and text in JSON files. Loki never updates model weights, never fine-tunes
  itself, and doesn't recursively rewrite its own brain. "Self-improving" means its
  *library* grows, not its *intelligence*.
- **It needs your LLM key.** All thinking happens through an OpenAI-compatible
  `chat/completions` endpoint you provide (`LOKI_API_KEY`). Without a key (or
  network), the loop can't run — the tests use a scripted stand-in brain instead.
- **Generated code runs locally, with your privileges.** The "sandbox" is a
  subprocess with a timeout, not a security boundary: no containers, no syscall
  filtering, no resource limits beyond the timeout. See Safety below.
- **Retrieval is keyword overlap, not semantic search.** Skill/lesson matching is
  simple token overlap — fast and dependency-free, but it won't catch synonyms or
  subtle relevance the way embeddings would.
- **It's only as good as the model behind it.** Bad plans, infinite fix loops (bounded
  by `--max-iters`), and confidently wrong code are all possible. The run reports in
  `runs/` exist so you can audit everything it did.

## Safety

- Generated code executes on **your machine** as **your user**. Treat every goal like
  handing a terminal to a clever intern: don't run it on machines you care about
  without reviewing, and never point it at goals involving credentials, destructive
  filesystem operations, or untrusted third parties.
- API keys are passed only in the `Authorization` header to the endpoint you configure,
  and are never written to logs, reports, or the skill library. `repr()` of the client
  masks the key.

---

## Project structure

```
loki-self-improving-agent/
├── loki/
│   ├── __init__.py      # package version
│   ├── __main__.py      # CLI: python -m loki "goal" [flags]
│   ├── agent.py         # the self-improvement loop + run reports
│   ├── llm.py           # thin OpenAI-compatible chat client (mockable)
│   ├── sandbox.py       # subprocess code execution with timeout
│   ├── skills.py        # persistent skill library + keyword retrieval
│   └── memory.py        # append-only experience log + lesson retrieval
├── examples/
│   ├── generate_examples.py      # regenerates the transcripts below
│   ├── example_run_word_count.md # illustrative: success on first try
│   └── example_run_csv_average.md# illustrative: fail → fix → learn
├── tests/               # 53 tests, fully mocked LLM, no network
├── Dockerfile
├── requirements.txt
└── .github/workflows/ci.yml
```

## Testing

```bash
pip install -r requirements.txt
pytest -q        # 53 tests, ~3s, no network, no API key needed
ruff check loki tests examples/generate_examples.py
```

The agent-loop tests use a scripted fake LLM, so the full plan → execute → reflect
cycle (including failure-and-retry and skill/lesson distillation) is tested
deterministically without spending a cent on API calls.

---

*Built as a portfolio project exploring agentic loops, lifelong learning, and honest
engineering: every claim in this README is backed by code and tests you can run.*

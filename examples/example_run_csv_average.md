> **Illustrative example.** This is a real end-to-end run of Loki's loop —
> prompt building, code extraction, sandboxed execution, and skill/lesson
> capture all ran for real. The LLM's replies were scripted (a stand-in
> "brain") to keep the example deterministic. Every code block below was
> actually executed in the sandbox. `$WORKDIR` stands in for the
> machine-specific working directory used when this was generated.

## What Loki said

- Howdy! Loki here — let's see what timeline this task takes us down. 🌀
- Goal for this timeline: "Compute the average price from data.csv and print it rounded to 2 decimals."
- Alright, I've got a plan cookin'. Writin' up the first attempt now…
- Spinnin' up the sandbox — attempt 1 of 5. Let's see if this timeline holds…
- Well, butter my biscuit — that timeline just pruned itself. Here's the damage:
- Traceback (most recent call last):
  File "$WORKDIR/run_20260920T093217Z/attempt_1.py", line 5, in <module>
    avg = sum(float(r["cost"]) for r in rows) / len(rows)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$WORKDIR/run_20260920T093217Z/attempt_1.py", line 5, in <genexpr>
    avg = sum(float(r["cost"]) for r in rows) / len(rows)
                    ~^^^^^^^^
KeyError: 'cost'
- Variant located! Takin' another crack at it…
- Spinnin' up the sandbox — attempt 2 of 5. Let's see if this timeline holds…
- Hot dog, that worked! Filing this one away in the archives…
- Output:
columns: ['product', 'price']
19.83
- New skill filed under 'csv_column_average'. The archives grow! 📚
- Lesson logged for future variants. They'll thank me later.

---

# Loki run report — ✅ SUCCESS

**Goal:** Compute the average price from data.csv and print it rounded to 2 decimals.
**Started:** 2026-09-20T09:32:17.874554+00:00  
**Ended:** 2026-09-20T09:32:18.431641+00:00  
**Iterations used:** 2

## Attempt 1 ❌

*exit_code=1, timed_out=False, elapsed=0.21s*

```python
import csv
from pathlib import Path

rows = list(csv.DictReader(Path("$WORKDIR/data.csv").open(encoding="utf-8")))
avg = sum(float(r["cost"]) for r in rows) / len(rows)
print(f"{avg:.2f}")
```

<details><summary>output</summary>

```
--- stdout ---
(empty)
--- stderr ---
Traceback (most recent call last):
  File "$WORKDIR/run_20260920T093217Z/attempt_1.py", line 5, in <module>
    avg = sum(float(r["cost"]) for r in rows) / len(rows)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$WORKDIR/run_20260920T093217Z/attempt_1.py", line 5, in <genexpr>
    avg = sum(float(r["cost"]) for r in rows) / len(rows)
                    ~^^^^^^^^
KeyError: 'cost'
```

</details>

## Attempt 2 ✅

*exit_code=0, timed_out=False, elapsed=0.34s*

```python
import csv
from pathlib import Path

with Path("$WORKDIR/data.csv").open(encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
print("columns:", list(rows[0].keys()))
avg = sum(float(r["price"]) for r in rows) / len(rows)
print(f"{avg:.2f}")
```

<details><summary>output</summary>

```
--- stdout ---
columns: ['product', 'price']
19.83
--- stderr ---
(empty)
```

</details>

## Skills added to the library

- `csv_column_average`

## Lessons logged

- always inspect CSV headers before assuming column names


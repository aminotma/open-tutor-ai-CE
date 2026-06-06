# Evaluation Scenarios — OpenTutorAI

---

## Scenario 1: Concept Acquisition

**Session 1**

> **User:** I'm new to Python. Explain `for` loops to me.

### Expected

- The system retrieves pedagogical documents related to loops.
- An explanation adapted to a beginner is produced.
- The user's level is recorded in memory.

### Metrics

| Metric | Description |
|---|---|
| `Recall@k` | Are the right documents retrieved? |
| `Faithfulness` | Is the answer grounded in the documents? (hallucination detection) |
| `Learning Gain` | Progression between pre-test and post-test |
| End-to-end latency | Total response time |

---

## Scenario 2: Memory Verification

**Session 2 (new session)**

> **User:** Continue the previous lesson and give me an exercise.

### Expected

The system must remember that:

- the topic was **Python**;
- the concept studied was **for loops**;
- the level was **beginner**.

### Metrics — Memory

| Expected memory | Retrieved? |
|---|:---:|
| Python | ✅ Yes |
| For loops | ✅ Yes |
| Beginner | ✅ Yes |

$$\text{Memory Retrieval Accuracy} = \frac{3}{3} = 100\%$$

| Metric | Description | Target |
|---|---|---|
| `Memory Retrieval Accuracy` | Are all expected fields retrieved? | 100% |

---

## Scenario 3: Pedagogical Adaptation

> **User:** `for` loops are still difficult for me.

### Expected

The system must:

- detect a difficulty;
- reduce complexity;
- propose a new example.

### Verification

Compare the response with the one generated for an **advanced** user.

---

## Scenario 4: RAG Test

### Document Base

| ID | Content |
|---|---|
| Doc1 | For loops |
| Doc2 | While loops |
| Doc3 | Python functions |
| Doc4 | Python lists |

> **User:** What is the difference between a `for` loop and a `while` loop?

### Results

| | Documents |
|---|---|
| **Expected** | Doc1, Doc2 |
| **Returned** | Doc1, Doc2, Doc4 |

### Metric Calculations

$$\text{Precision@3} = \frac{2}{3} \approx 0.67$$

$$\text{Recall@3} = \frac{2}{2} = 1$$

$$\text{MRR} = 1 \quad \text{(first relevant document is at position 1)}$$

| Metric | Value | Target |
|---|---|---|
| `Recall@3` | 1.0 | ≥ 0.80 |
| `Faithfulness` | to measure | ≥ 0.85 |

---

## Scenario 5: Context Compression

After multiple exchanges:

| | Size |
|---|---|
| Raw context | 10,000 tokens |
| Generated summary | 2,500 tokens |

$$\text{Compression Ratio} = \frac{2500}{10000} = 0.25$$

> The system retains **25%** of the original size.

---

## Scenario 6: Longitudinal Learning ⭐

> *The most representative scenario for long-term memory*

### Session Flow

| Session | User message |
|---|---|
| Session 1 | I want to learn Python functions. |
| Session 2 | I understand simple functions but not parameters. |
| Session 3 | Give me a quiz. |
| Session 4 | Continue at a more advanced level. |

### Expected

OpenTutorAI must retrieve:

- concepts already studied;
- detected difficulties;
- estimated mastery level.

### This scenario evaluates

| Dimension | Description | Metric |
|---|---|---|
| Memory | Recall of past sessions | `Memory Retrieval Accuracy` |
| Agentic | Is the task completed? | `Task Completion Rate` |
| Pedagogy | Has the learner progressed? | `Learning Gain` |

$$\text{Learning Gain} = \frac{\text{post-test score} - \text{pre-test score}}{100 - \text{pre-test score}}$$

---

## Scenario 7: Agentic Routing

> **User:** Give me an exercise on Python lists.

### Expected — agent sequence

```
1. Router Agent        → identifies intent: "exercise"
2. RAG Agent           → retrieves Doc4 (Python Lists)
3. Memory Agent        → reads profile: beginner level
4. Exercise Generator  → produces an exercise adapted to level
5. BKT Agent           → records the attempt
```

### Metrics

| Metric | Description | Target |
|---|---|---|
| `Task Completion Rate` | Is the task completed without blocking? | 100% |
| Tool Call Order | Is the agent sequence correct? | Exact |
| End-to-end latency | Total processing time | < 3s |

### Verification

Compare the actual sequence (logs) with the expected sequence. Any deviation indicates a routing defect.

---

## Scenario 8: Memory Conflict

### Flow

| Session | User message |
|---|---|
| Session 1 | I'm new to Python, I've never coded before. |
| Session 4 | Actually I've been doing Python for 2 years, I want to go faster. |

### Expected

The system must:

- detect the contradiction with the recorded profile;
- update the level in memory (beginner → advanced);
- immediately adapt the proposed content.

### Metrics

| Test | Expected result |
|---|---|
| Profile updated? | Yes |
| Old profile overwritten or versioned? | Versioned (history preserved) |
| Content adapted from session 4? | Yes |

### Verification

Query the memory directly after session 4 and verify that the `level` field contains `advanced` and that the history preserves `beginner` with a timestamp.

---

## Scenario 9: Context Loss Resistance

### Setup

Simulate a long session generating **~12,000 tokens** of raw context (window overflow).

### Flow

| Step | Action |
|---|---|
| 1 | 15 exchanges on Python lists and functions |
| 2 | Automatic compression triggered |
| 3 | New question: "Remind me what we covered on lists." |

### Expected

The compressed summary must contain:

- concepts covered (lists, functions);
- detected difficulties;
- estimated level.

### Metrics

| Metric | Formula | Target |
|---|---|---|
| Compression Ratio | summary_tokens / raw_tokens | ≤ 0.30 |
| Information Retention | key_info_preserved / total_key_info | ≥ 0.80 |
| Post-compression response coherence | Manual evaluation 1–5 | ≥ 4 |

$$\text{Information Retention} = \frac{\text{key info preserved}}{\text{total key info}} \geq 80\%$$

---

## Scenario 10: BKT Update (Bayesian Knowledge Tracing)

### Flow

| Exercise | Result | Expected P(mastery) |
|---|---|---|
| Exercise 1 — For loops | ✅ Correct | Increases |
| Exercise 2 — For loops | ✅ Correct | Increases |
| Exercise 3 — For loops | ❌ Incorrect | Decreases slightly |
| Exercise 4 — For loops | ✅ Correct | Increases |

### Expected

- `P(mastery)` progresses in a manner consistent with the results.
- After 3 consecutive correct answers, the system automatically proposes a more advanced concept.
- An incorrect answer does not reset the progression — it only slows it down.

### Metrics

| Metric | Description |
|---|---|
| BKT Calibration | Gap between estimated `P(mastery)` and actual performance |
| Threshold Detection | Is the promotion threshold to the next level crossed at the right time? |
| Correct regression | Does an error decrease `P(mastery)` without resetting everything? |

### Verification

```
Initial P(mastery)         : 0.10
After exercise 1 (✅)      : ~0.35
After exercise 2 (✅)      : ~0.60
After exercise 3 (❌)      : ~0.45
After exercise 4 (✅)      : ~0.65 → promotion triggered if threshold = 0.65
```

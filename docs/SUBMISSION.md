# Cell Crime Scene — Submission

**An autonomous agent that investigates, repairs and verifies cell-segmentation failures in fluorescence
microscopy, and keeps a full audit trail for human review.**

Research image-analysis quality control. Not a diagnostic or clinical tool.

## The problem

Researchers count and measure cell nuclei with threshold-based segmentation pipelines. When nuclei touch,
those pipelines merge them into one object, so counts come out low and size statistics are skewed. Today
the researcher spots it by eye, tweaks parameters, reruns and compares, one image at a time.

**Who it is for:** _[name, role, lab — the researcher who confirmed this problem, plus a one-line quote]_

## What the agent does

```
inspect → recall → diagnose → hypothesis tournament (verify every candidate) → refine winner → accept / abstain
        → suspect lineup → report → human review
```

1. **Inspect** (Python): counts objects and measures area and solidity; flags oversized or concave objects.
2. **Recall** (MongoDB Atlas hybrid search): retrieves past verified repairs with matching failure tags and a
   similar image fingerprint, and the tool that fixed each one.
3. **Diagnose** (Gemini 4 Argon): explains *why* the segmentation failed, with each root cause tied to
   evidence (region areas, solidity, SNR, noise, crowding) and a likelihood.
4. **Hypothesis tournament** (Gemini 4 Argon designs it, Python runs it): each round, the agent proposes
   2–3 *competing* hypotheses, for example "touching round nuclei, so split on shape", "a dim seam between
   nuclei, so split on intensity", "thin bridges, so erode". Each one is tested with an allowlisted tool on a
   copy. The original image and mask are checksummed and never modified.
5. **Verify every candidate** (Python, independent of the model): instance F1, count error, foreground IoU
   and integrity checks against a fixed acceptance policy. Candidates are ranked on a leaderboard. Gemini
   reads the leaderboard, refines the winner or tests new hypotheses, and accepts or abstains. At most 3
   rounds. "Accept" is refused unless a candidate passed verification.
6. **Suspect lineup**: every flagged region gets its own verdict against the reference annotation (solved,
   partly split, still merged, over-split, or correctly left whole), with before/after/truth crops.
7. **Report and review**: a before/after slider, a change map (red = merged outlines, green = new cuts),
   metrics, the agent's reasoning and its stated uncertainties, and a downloadable evidence report. A human
   approves or rejects the result.

## Agent tools (allowlist)

The agent cannot run arbitrary code. It names a tool, and every parameter is validated and clamped to the
bounds below before execution (`backend/tools/registry.py`).

| Tool | What it does | Parameters (bounds) |
|---|---|---|
| `watershed_split` | Marker-controlled watershed on a distance or intensity landscape to split merged nuclei | `min_distance` 3–25, `sigma` 0–3, `landscape` distance/intensity, `target` suspicious/all |
| `erosion_split` | Erode to break thin bridges, regrow cores within the original outline | `radius` 1–8, `target` |
| `remove_small_objects` | Drop debris fragments | `min_size` 5–500 |
| `resegment_threshold` | Re-segment from scratch (Otsu, Li or local threshold) | `method`, `sigma` 0–4, `min_size` |
Each tool can work on the original baseline or refine the current winner (`base`). The planner's actions
are `experiment` (a list of competing candidates), `accept` (send the best verified attempt for review) and
`abstain` (flag the case as unresolved).

## Verification signal

Acceptance policy (`backend/tools/verify_result.py`). A candidate passes only if all of these hold:

- instance F1 (one-to-one matching at IoU > 0.5) improves by at least 0.02
- foreground IoU drops by no more than 0.02
- absolute count error is not worse
- the original image checksum is unchanged, the mask shape matches, the mask is not empty, the object count
  is plausible, and at least 85% of the foreground overlaps the baseline

The agent never sees the reference mask. Only the verifier uses it. Without a reference mask, a result is
reported as "unverified" and cannot be marked as passed.

## Results on held-out real images

12 BBBC038 fluorescence images, selected by the importer because their baseline merges nuclei, and never
used during development (`python backend/scripts/evaluate.py --dir datasets/heldout_dsb`):

| | Before | After |
|---|---|---|
| Verified repairs | – | 12 / 12 |
| Mean instance F1 | 0.785 | 0.887 |
| Mean \|count error\| | 8.0 | 4.1 |
| Mean foreground IoU | 0.828 | 0.828 |

These figures come from the offline heuristic planner, which is the baseline the Gemini agent has to beat.
_[Add the same table for gemini-4-argon once it has run.]_

## Gemini models and how they are used

| Model | Role |
|---|---|
| `gemini-4-argon` | Lead investigator. One call per tournament round: multimodal input (measurements as JSON, the microscopy image, the current segmentation overlay, every earlier leaderboard), structured JSON output validated against a schema (root causes, competing candidates, or accept/abstain). Also writes the final report from the recorded metrics. |

- **Interactions API** (`client.interactions.create`), with `previous_interaction_id` chaining, so the
  investigation keeps server-side state across turns.
- `thinking_level="high"`. No temperature or other deprecated sampling settings.
- **Guardrails around the model:** allowlisted tools, clamped parameters, independent verification, refusal
  of "accept" without a passing attempt, a timeout per call, and a deterministic fallback planner. Every
  step records which planner made it.

## MongoDB Atlas

MongoDB Atlas is the system of record and the agent's memory.

| Collection | Stores |
|---|---|
| `cases` | Case metadata, status, failure tags, image fingerprint, final report |
| `assets` | File references, SHA-256 checksums, versions (originals vs derived) |
| `analysis_runs` | Every attempt: tool, parameters, measurements, verification verdict |
| `agent_steps` | The full audit trail: each decision, tool call, guardrail, error and review |
| `evidence` | Suspicious regions, hypotheses, verification findings |
| `reviews` | Human approvals and rejections |

| Atlas feature | Used for |
|---|---|
| **Atlas Search** | Case search with fuzzy matching (titles, notes, tags, hypotheses, reports) |
| **Atlas Vector Search** | A 10-dimension fingerprint of each image and its baseline mask (noise, contrast, crowding, nucleus size, size spread, concavity, share of merged-looking objects); finds past cases that look alike |
| **Hybrid Search** (`$rankFusion`) | Fuses tag text search and fingerprint vector search to retrieve past verified repairs, which are passed to the agent before its first decision |

## Human in the loop

- Nothing is overwritten: repairs are new, versioned files, and the originals are checksummed.
- Only a case whose repair passed verification can be approved.
- The agent abstains rather than guessing, and says what remains uncertain.

## Stack

Next.js + TypeScript (dashboard) · FastAPI + Python (orchestration, tools) · scikit-image, SciPy, NumPy,
OpenCV (image analysis) · Gemini 4 Argon (planning) · MongoDB Atlas (storage, search, memory)

## Data

BBBC038 / 2018 Data Science Bowl, Broad Bioimage Benchmark Collection (Caicedo et al., *Nature Methods*
2019). The repository also includes synthetic cases generated by `datasets/generate_synthetic.py`.

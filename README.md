# Cell Crime Scene

An autonomous agent that investigates segmentation failures in fluorescence-microscopy nucleus images,
repairs them with allowlisted image-analysis tools, verifies each repair independently against reference
masks, and keeps a full audit trail for human review.

This is a research image-analysis quality-control tool. It is not a diagnostic or clinical tool.

## How it works

```
upload image + baseline mask (+ optional reference mask)
  -> inspect      Python: counts, areas, solidity; flags oversized / concave objects
  -> decide       Gemini (or offline heuristic): hypothesis + one allowlisted tool with parameters
  -> repair       Python: watershed_split / erosion_split / remove_small_objects / resegment_threshold
  -> verify       Python: instance F1, count error, foreground IoU, integrity checks vs acceptance policy
  -> retry / accept / abstain   (bounded by MAX_ATTEMPTS)
  -> report       before/after overlays, metrics, reasoning, uncertainties
  -> human review approve / reject
```

- The agent never sees the reference mask; only the verifier uses it.
- "Accept" is refused unless an attempt passed verification.
- Parameters are clamped to the bounds in `backend/tools/registry.py`; the agent cannot run arbitrary code.
- Originals are checksummed and never modified.

## Results (held-out real images)

12 BBBC038 fluorescence images not used during development, offline heuristic planner:

| | Before | After |
|---|---|---|
| Verified repairs | – | 11 / 12 (1 abstained) |
| Mean instance F1 | 0.785 | 0.882 |
| Mean \|count error\| | 8.0 | 4.5 |
| Mean foreground IoU | 0.828 | 0.828 |

Reproduce with `python backend/scripts/evaluate.py --dir datasets/heldout_dsb`.

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
cd frontend && npm install
cp .env.example .env                               # optional: Gemini key, Atlas URI
```

Run:

```bash
cd backend && ../.venv/Scripts/python -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev                         # http://localhost:3000
```

## Data

- `sample_cases/` – demo cases: 4 synthetic + 6 real BBBC038 fluorescence fields.
- `datasets/heldout/` – 12 synthetic held-out cases.
- `datasets/heldout_dsb/` – 12 real BBBC038 held-out cases.

Re-create the real cases from the Broad Bioimage Benchmark Collection
([BBBC038](https://bbbc.broadinstitute.org/BBBC038), Caicedo et al., Nature Methods 2019):

```bash
curl -L -o datasets/raw/bbbc038/stage1_train.zip https://data.broadinstitute.org/bbbc/BBBC038/stage1_train.zip
# extract to datasets/raw/bbbc038/stage1_train/, then:
python datasets/import_dsb2018.py datasets/raw/bbbc038/stage1_train --dev 6 --heldout 12
```

The importer keeps only fluorescence images whose Otsu baseline merges at least two nuclei.

## MongoDB Atlas

Set `MONGODB_URI` in `.env`, then run once:

```bash
python backend/scripts/setup_atlas.py    # collections + Atlas Search index + Atlas Vector Search index
python backend/scripts/seed_history.py   # optional: run the sample cases to build investigation memory
```

Collections: `cases`, `assets`, `analysis_runs`, `agent_steps`, `evidence`, `reviews`.

| Atlas feature | Used for |
|---|---|
| Atlas Search (`ccs_search`) | Case search box (`/api/search`), fuzzy matching on titles, notes, tags, hypotheses, reports |
| Atlas Vector Search (`ccs_vector`) | Each case stores a 10-number fingerprint of its image and baseline mask (noise, contrast, nucleus size, size spread, concavity, share of merged-looking objects). Finds past cases that look alike. |
| Hybrid Search (`$rankFusion`) | Before its first decision, the agent gets past verified repairs ranked by matching failure tags and similar fingerprints, plus the tool that fixed each one. |

## Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
```

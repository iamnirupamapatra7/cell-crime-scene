# 3-minute demo script

No slides. Everything happens in the app and the Atlas console.

## Before going on stage
- [ ] Backend and frontend running, `/api/health` shows `planner: gemini`, `model: gemini-4-argon`, `storage: mongodb-atlas`
- [ ] Atlas history seeded (`seed_history.py`), so "similar past investigations" has results
- [ ] One finished case already open in a second tab, in case the live run is slow
- [ ] Atlas console logged in, open on `cell_crime_scene → agent_steps`
- [ ] Demo case: `dsb_06c779330d` (real BBBC038 image, 3 merged nuclei, fixed on the first attempt)

## Script

**0:00–0:25 · The problem (home page)**
> "[Name] counts nuclei in fluorescence images for [their research]. Their pipeline merges touching nuclei,
> so counts come out low, and fixing it means tweaking and rerunning by hand, image by image.
> This is one of those images: real data, the reference has 30 nuclei, the pipeline found 22."

**0:25–0:55 · Start the investigation**
- Click sample `dsb_06c779330d`.
> "The agent measures the mask first. Red boxes are objects that are too big or too concave to be one nucleus.
> It also pulls past repairs from MongoDB Atlas with hybrid search: same failure type, similar-looking image."
- Point at the "Retrieved 3 similar past investigations" step.

**0:55–1:45 · Gemini decides and repairs**
- Point at the Gemini decision in the timeline.
> "Gemini 4 Argon sees the image, the overlay and the numbers. It forms a hypothesis and chooses one tool from
> an allowlist with bounded parameters. It can't run arbitrary code."
- Point at "Ran watershed_split", then the updated overlay.

**1:45–2:20 · Verification**
- Open the metrics panel.
> "Pass or fail is not Gemini's call. Python compares the result with the human-annotated reference,
> which Gemini never saw. F1 went up, the count error dropped, and the original image checksum is unchanged.
> When an attempt fails, Gemini reads why and adjusts. If nothing passes, it abstains instead of guessing."
- If there's a failed attempt, show its red check.

**2:20–2:45 · Audit trail and human approval**
- Switch to Atlas: `agent_steps` for this case.
> "Every decision, tool call and verdict is stored in Atlas."
- Back in the app: click **Approve**.
> "A person makes the final call."

**2:45–3:00 · Close**
> "On 12 held-out real images it verified 11 repairs and abstained on the one it couldn't fix.
> Next: more failure types and batch runs across a whole plate."

## Likely questions
- **Why do you need Gemini if the tools are classical?** The tools are fixed. Gemini chooses which one, with
  which parameters, on which regions, and reads the verification feedback to adjust. It also has to tell
  merged nuclei from genuinely large ones by looking at the image.
- **What if Gemini is wrong?** The verifier rejects it. "Accept" is refused without a passing attempt,
  parameters are clamped, and the original is never modified.
- **What if there's no reference mask?** The result is labelled "unverified" (a proxy check only) and cannot
  be marked as passed.
- **Is this diagnosis?** No. It's quality control of a research image-analysis step, with a human approving.

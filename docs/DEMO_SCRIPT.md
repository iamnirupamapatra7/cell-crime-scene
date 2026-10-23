# 3-minute demo script

No slides. Everything happens in the app and the Atlas console.

## Before going on stage
- [ ] Backend and frontend running, `/api/health` shows `planner: gemini`, `model: gemini-4-argon`, `storage: mongodb-atlas`
- [ ] Atlas history seeded (`seed_history.py`), so "similar past investigations" has results
- [ ] One finished case already open in a second tab, in case the live run is slow
- [ ] Atlas console logged in, open on `cell_crime_scene → agent_steps`
- [ ] Demo case: `dsb_44ab6a09ee` (real BBBC038 image: reference 34 nuclei, pipeline finds 26; F1 0.667 → 0.879)

## Script

**0:00–0:25 · The problem (home page)**
> "[Name] counts nuclei in fluorescence images for [their research]. Their pipeline merges touching nuclei,
> so counts come out low, and fixing it means tweaking and rerunning by hand, image by image.
> This is one of those images: real data, the reference has 34 nuclei, the pipeline found 26."

**0:25–0:55 · Start the investigation**
- Click sample `dsb_44ab6a09ee`.
> "The agent measures the mask first. Red boxes are objects that are too big or too concave to be one nucleus.
> It also pulls past repairs from MongoDB Atlas with hybrid search: same failure type, similar-looking image."
- Point at the "Retrieved 3 similar past investigations" step.

**0:55–1:45 · Diagnosis and hypothesis tournament**
- Point at **Root-cause diagnosis**.
> "Gemini 4 Argon first explains why the pipeline failed, with evidence: these regions are three times a
> normal nucleus and concave."
- Point at **Hypothesis tournament**, round 1.
> "Then it runs experiments like a scientist: three competing explanations, each tested with an allowlisted
> tool. It can't run arbitrary code. Every candidate is verified, and here's the leaderboard. In round 2 it
> refines the winner."
- Drag the **before/after slider** across the image.

**1:45–2:20 · Verification and the suspect lineup**
- Scroll to the **Suspect lineup**.
> "Pass or fail is not Gemini's call. Python checks every flagged region against the human-annotated
> reference, which Gemini never saw. Suspect 1: three nuclei in truth, three after repair, solved. Suspect 4
> was one big nucleus, correctly left alone. Suspect 6 is still merged, and it says so."
- Point at the F1 and count metrics.

**2:20–2:45 · Audit trail and human approval**
- Switch to Atlas: `agent_steps` for this case.
> "Every decision, tool call and verdict is stored in Atlas."
- Back in the app: click **Approve**.
> "A person makes the final call."

**2:45–3:00 · Close**
> "On 12 held-out real images, every repair passed independent verification, and F1 went from 0.79 to 0.89.
> You can download the full evidence report. Next: more failure types and batch runs across a whole plate."

## Likely questions
- **Why do you need Gemini if the tools are classical?** The tools are fixed. Gemini chooses which one, with
  which parameters, on which regions, and reads the verification feedback to adjust. It also has to tell
  merged nuclei from genuinely large ones by looking at the image.
- **What if Gemini is wrong?** The verifier rejects it. "Accept" is refused without a passing attempt,
  parameters are clamped, and the original is never modified.
- **What if there's no reference mask?** The result is labelled "unverified" (a proxy check only) and cannot
  be marked as passed.
- **Is this diagnosis?** No. It's quality control of a research image-analysis step, with a human approving.

# Roadmap: ideas and TODOs

Nothing on this page is implemented. These are ideas to explore once there is evidence to decide them.

## Idea 1: route wiki tasks to models and effort levels, per provider

Maintaining a wiki mixes two kinds of work, and they probably do not need the same model:

| Task class | Examples | Hypothesis |
|---|---|---|
| Mechanical | `wiki-sources sync`, copying raw files, frontmatter, index and log lines, structural lint, translating a clear page | A mid or small model at low/medium effort is as good as a large one |
| Reading at volume | Summarising many files with a fixed shape, first pass over a big source | Small or mid model, ideally as a subagent with its own context |
| Judgment | Deciding which document is authoritative, spotting contradictions and stale docs, designing a check that proves a claim, synthesis pages, semantic lint | A large model at medium/high effort; the loss with a weaker model is silent (the wiki passes lint but repeats its sources' mistakes) |
| First ingest of a new, large source | Mix of the above | Large model; incremental re-syncs afterwards can drop a tier |

Write the routing as tiers (large / mid / small) and effort levels, not model names, so the same table applies to every provider an agent like OpenCode can use, and survives model releases. Each provider then maps its own models onto the tiers in local config.

Open questions:

- Do effort levels mean the same across providers? Probably not; the mapping may need to be per provider and per model.
- Where does the routing live: in each wiki's `SCHEMA.md`, in the agent's config, or in this repo as a default the wiki can override?
- Can an agent switch model mid-task (for example a subagent for reading), and does that lose prompt-cache benefits that outweigh the savings?

## Idea 2: record which model and effort performed each wiki operation

Provenance for the operations, not only for the sources. When a page was written or changed, keep a note of the model tier, the provider, the exact model id and the effort that did it.

Possible places, from least to most intrusive:

1. **The log line**, which already exists for every operation: `## [YYYY-MM-DD] ingest | <source> | by: <provider>/<model-id> effort=<level>`.
2. **The git commit** that carries the operation, as a trailer (`Wiki-Model: ...`, `Wiki-Effort: ...`), so `git log` answers "who wrote this page".
3. **Page frontmatter** (`updated_by:`), most visible but noisy: every edit rewrites it and diffs grow.

Uses:

- Re-check, with a stronger model, pages that only a weaker model has touched.
- Measure quality per model over time (feeds the test suite below).
- Explain differences between two wikis built from the same sources.

Constraints:

- The agent may not reliably know which model is serving it (fallbacks, model switches). Record what the harness reports, or nothing; never a guess.
- Never record secrets, account ids or user data in these tags.

## TODO: a test suite to decide between models and effort levels

Neither idea should be adopted on intuition. Needed first: an eval that shows, for each task class, where a cheaper tier holds quality.

Sketch:

- **Fixtures:** frozen snapshots of real sources (pinned commits through `wiki-sources`) with a reference wiki built from them.
- **Checks per task class:**
  - Mechanical: structural lint passes; frontmatter complete; index and log updated; `verify` clean.
  - Judgment: a checklist of planted or known findings that a good ingest must surface (an outdated doc tree, a broken template, a contradiction between two sources, a wrong install path). Score how many each run finds, and count unsupported claims.
- **Matrix:** provider × model tier × effort, same fixture, several runs each (outputs vary between runs).
- **Cost:** tokens and wall time per completed task, not per request.
- **Output:** a small table per task class: the cheapest setting whose score stays within an agreed margin of the best one.

Open: who grades judgment checks (a fixed checklist, a strong model as grader, or a human), and how to keep fixtures from leaking into the models being tested.

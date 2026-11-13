# Composing wikis

One wiki per repository, used from other projects on demand. The `llm-wiki` skill resolves one wiki at a time (a path you name, then project instructions, then global instructions, then `./wiki/`) and never merges two silently. Composition is therefore explicit.

## 1. Each wiki is a self-contained repo

```text
<topic>-wiki/
├── AGENTS.md          pointer for OpenCode (and others)
├── CLAUDE.md          same pointer for Claude Code (or a symlink to AGENTS.md)
├── wiki/              SCHEMA.md, index.md, log.md, pages
├── raw/               sources, with raw/sources.json for git mirrors
└── .agents/skills/wiki-sources/   (optional, per-project install)
```

It works on its own: clone it, open it in either agent, and it is a normal project wiki.

## 2. Mount external wikis read-only, on demand

Clone each external wiki next to your projects, shallow and blob-less so it costs little:

```bash
git clone --depth 1 --filter=blob:none https://github.com/<owner>/<topic>-wiki.git ~/wikis/<topic>-wiki
```

Refresh with `git -C ~/wikis/<topic>-wiki pull --depth 1`. Prefer this to git submodules: submodules pin a version but add friction to every clone and pull of the host project, which is not worth it for reading on demand.

## 3. Declare them in the host project

In the host wiki's `wiki/SCHEMA.md`:

```markdown
## External wikis (read-only)

| Name | Repo | Local path | Owns |
|---|---|---|---|
| opencode | github.com/<owner>/opencode-wiki | ~/wikis/opencode-wiki | OpenCode: CLI, config, agents, skills |

- Query one with `wiki_search.py --wiki <local path>/wiki "<query>"`, or read its `wiki/index.md`.
- Never write to an external wiki from here. Ingest into the wiki that owns the topic, in its own repo.
- Cite external pages with a plain link and the external wiki name, e.g. `[opencode: skills](~/wikis/opencode-wiki/wiki/concepts/skills.md)`, not `[[wikilinks]]` (they are local to one wiki and lint would flag them).
- A synthesis that combines several wikis lives in the host wiki and lists every external page it used.
```

And one line in the host's `CLAUDE.md` / `AGENTS.md`:

```markdown
External wikis are listed in `wiki/SCHEMA.md` ("External wikis"). Read them only when a question is about their topic, and never write to them.
```

## 4. Cloud sessions (claude.ai/code)

A cloud session sees only the repositories attached to it. Attach the external wiki repo to the session (or the environment), then clone it as in step 2. Cloned copies vanish with the container; only what is committed and pushed survives.

## Why not one big wiki?

Separate repos keep each wiki's index small (the main scaling limit of the pattern), let each topic have its own schema and update cadence, and make it obvious which wiki owns a fact. A global personal wiki (`~/wiki/`) remains a good choice for knowledge that is only yours and cuts across all topics.

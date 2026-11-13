# llm-wiki

Shared tooling and conventions for LLM-maintained wikis, usable from Claude Code and OpenCode (and any agent that reads [Agent Skills](https://agentskills.io) and can run a shell).

| Piece | What it is |
|---|---|
| [`.claude/skills/wiki-sources/`](.claude/skills/wiki-sources/SKILL.md) | Skill + script that mirrors git repositories into a wiki's `raw/` **incrementally**: `check` uses `git ls-remote` only, `sync` downloads only the changed files through a throwaway partial clone (`--depth=1 --filter=blob:none`, one batched blob fetch). |
| [`docs/composing-wikis.md`](docs/composing-wikis.md) | How to keep each wiki in its own repo and use several from one project on demand. |
| [`docs/roadmap.md`](docs/roadmap.md) | Ideas not yet implemented: routing tasks to models and effort levels per provider, recording which model did each operation, and the test suite needed to decide. |

The wiki format itself (pages, `SCHEMA.md`, ingest/query/lint) comes from the `llm-wiki` skill; this repo adds to it, it does not replace it.

## Where agents look for skills

| Location | Claude Code | OpenCode |
|---|---|---|
| `~/.claude/skills/<skill>/` (user) | yes | yes (compatibility) |
| `~/.agents/skills/<skill>/` (user) | no | yes |
| `~/.config/opencode/skills/<skill>/` (user) | no | yes |
| `.claude/skills/<skill>/` (project) | yes | yes (compatibility) |
| `.agents/skills/<skill>/` (project) | no (link it) | yes |

OpenCode column: OpenCode's own docs (`services/site/src/docs/content/skills.mdx`, anomalyco/opencode @ 5b131f5, 2026-11-13). OpenCode also takes extra skill directories in the `skills` array of `opencode.json`. Setting `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` stops it reading `.claude/skills`.

## Install

The skill lives in `.claude/skills/`, which both Claude Code and OpenCode read (see the table above). Nothing has to be copied or linked into the projects that use it.

### Cloud sessions (claude.ai/code)

Attach `hiebra/llm-wiki` to the session, or add it to the environment's repositories so every session there starts with it. Claude Code loads the skill from the attached repo.

### Once per machine (both agents)

```bash
git clone --depth 1 https://github.com/hiebra/llm-wiki.git ~/src/llm-wiki
```

```bash
mkdir -p ~/.claude/skills && ln -s ~/src/llm-wiki/.claude/skills/wiki-sources ~/.claude/skills/wiki-sources
```

Both Claude Code and OpenCode now see the skill in every project. Update with `git -C ~/src/llm-wiki pull`.

### Per project, pinned with the project (optional)

Only if a project must carry its own pinned copy. From the project root, let the tool install itself as one more tracked source; `--raw-dir .` mirrors the upstream path at the same place in your project:

```bash
python3 ~/src/llm-wiki/.claude/skills/wiki-sources/scripts/wiki_sources.py add llm-wiki-tools https://github.com/hiebra/llm-wiki.git --raw-dir . --branch main --path .claude/skills/wiki-sources
```

Later updates are incremental like any other source:

```bash
python3 .claude/skills/wiki-sources/scripts/wiki_sources.py sync llm-wiki-tools
```

## Requirements

Python 3.9+, a git with partial-clone support (tested with 2.43.0), a remote that allows fetching commits and blobs by id (GitHub does).

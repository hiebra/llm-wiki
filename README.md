# llm-wiki

Shared tooling and conventions for LLM-maintained wikis, usable from Claude Code and OpenCode (and any agent that reads [Agent Skills](https://agentskills.io) and can run a shell).

| Piece | What it is |
|---|---|
| [`.agents/skills/wiki-sources/`](.agents/skills/wiki-sources/SKILL.md) | Skill + script that mirrors git repositories into a wiki's `raw/` **incrementally**: `check` uses `git ls-remote` only, `sync` downloads only the changed files through a throwaway partial clone (`--depth=1 --filter=blob:none`, one batched blob fetch). |
| [`docs/composing-wikis.md`](docs/composing-wikis.md) | How to keep each wiki in its own repo and use several from one project on demand. |

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

### Once per machine (both agents)

```bash
git clone --depth 1 https://github.com/hiebra/llm-wiki.git ~/src/llm-wiki
```

```bash
mkdir -p ~/.claude/skills && ln -s ~/src/llm-wiki/.agents/skills/wiki-sources ~/.claude/skills/wiki-sources
```

Both Claude Code and OpenCode now see the skill in every project. Update with `git -C ~/src/llm-wiki pull`.

### Per project, versioned with the project (recommended for shared repos)

From the project root, let the tool install itself as one more tracked source. `--raw-dir .` mirrors the upstream path at the same place in your project:

```bash
python3 ~/src/llm-wiki/.agents/skills/wiki-sources/scripts/wiki_sources.py add llm-wiki-tools https://github.com/hiebra/llm-wiki.git --raw-dir . --branch main --path .agents/skills/wiki-sources
```

```bash
mkdir -p .claude/skills && ln -s ../../.agents/skills/wiki-sources .claude/skills/wiki-sources
```

OpenCode reads `.agents/skills/` directly; the link is for Claude Code (OpenCode reads it too, so you never need two copies). Later updates are incremental like any other source:

```bash
python3 .agents/skills/wiki-sources/scripts/wiki_sources.py sync llm-wiki-tools
```

On Windows, committed links need `git config --global core.symlinks true` and Developer Mode; otherwise copy the folder.

## Requirements

Python 3.9+, a git with partial-clone support (tested with 2.43.0), a remote that allows fetching commits and blobs by id (GitHub does).

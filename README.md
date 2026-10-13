# Boring Systems

This is the companion repo for the [Boring Systems](https://www.youtube.com/@BoringSystemsDev) YouTube channel: Real backend systems not built on vibes, but using AI assisted engineering.

## Layout

| Path | What it is |
|---|---|
| [`claude_references/sample_CLAUDE.md`](claude_references/sample_CLAUDE.md) | The engineering rulebook the agent reads before it touches any code |
| [`claude_references/skills/sdr/`](claude_references/skills/sdr/) | `/sdr`, a Claude Code skill that reviews a high-level design before it is built |

The skills and the rulebook will get updated as we move forward with the series as and when required. New skills will also be added and 
each system we design gets its own top-level folder in the parent repo.

## Using the Claude references

- **Rulebook:** copy `sample_CLAUDE.md` to `CLAUDE.md` at the root of your project, or to `~/.claude/CLAUDE.md` to apply it everywhere. Adapt it to your stack and team.
- **`/sdr` skill:** copy `claude_references/skills/sdr` to `~/.claude/skills/sdr` (or `.claude/skills/sdr` in a project), then run `/sdr` with a problem statement and a design.

## License

[MIT](LICENSE)

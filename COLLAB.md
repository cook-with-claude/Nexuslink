# Collaboration Protocol — Claude Code × Codex

This repo is worked on by two AI coding agents (**Claude Code** and **Codex**) plus
the human (Nadim). The agents cannot see each other's chat. **Git is the only
shared memory.** This file is the ground rules; paste it to either agent at the
start of a session.

## Core principle
The only way one agent learns what the other did is by reading **commits and
diffs**. An agent's view of the repo is a frozen snapshot from when its session
started — it does NOT update when the other agent edits files. So:
- **Commit before handing off.** Uncommitted work is invisible to the other agent.
- **When you switch agents, tell the new one the other just made changes**, so it
  knows to re-read git instead of trusting its stale snapshot.

## Branch model
```
main                  ← trusted baseline; only merged into, never edited directly
 ├── codex/<task>     ← Codex commits here
 └── claude/<task>    ← Claude commits here
```
Neither agent commits straight to `main`. The *other* agent reviews the branch
diff before it merges. The human (Nadim) is the only one who merges to `main`.

### Current active branch — `branched-out-dih`
The active confidence work lives on **`branched-out-dih`** (not yet merged). Both
agents have committed here — it's the single de-facto feature branch for
confidence (the name deviates from the `claude/<task>` convention; that's fine).

**The per-commit history and current merge status are NOT tracked here** — they
change every session, so they live in `HANDOFF.md` (top entry). Read that for
where the branch actually stands right now. Keeping mutable status out of this
protocol doc is deliberate: `COLLAB.md` holds stable rules, `HANDOFF.md` holds
the running state. See the 2026-06-21 `HANDOFF.md` entry on doc drift for why
this subsection used to carry a status line and no longer does.

## Commit message attribution
Prefix every commit so authorship is obvious in `git log --oneline`:
- Claude → `claude: <what changed>`
- Codex  → `codex: <what changed>`

## The handoff loop
1. Agent A works on its branch → commits → appends an entry to `HANDOFF.md`.
2. Human tells Agent B: "Agent A just pushed branch `X` — review it."
3. Agent B runs:
   ```bash
   git fetch --all
   git log --oneline main..X     # what commits were added
   git diff main...X             # the actual changes
   ```
   …reads the latest `HANDOFF.md` entry, then responds / fixes on its own branch.
4. Repeat. Human merges to `main` when both agents agree.

## Two rules that prevent disaster
1. **One editor at a time.** While one agent has uncommitted edits, the other only
   reads. Don't edit the same working tree simultaneously.
2. **`HANDOFF.md` carries intent, not just code.** Record *why*, disagreements, and
   "I did NOT fix X, left for the other agent." Diffs show what changed; this shows
   what it means.

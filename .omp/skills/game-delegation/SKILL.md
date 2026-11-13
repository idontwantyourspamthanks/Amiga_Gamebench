---
name: game-delegation
description: How to delegate Amiga game reverse-engineering and patching work in gamebench to subagents so the results are trustworthy. Covers model routing, the evidence contract, task template, memory/blob allocation, FS-UAE concurrency, provider-failure handling, and the verification the lead must re-run. Use before spawning any task/smol/tiny agent in this project.
---

# Delegating game work to subagents

## Model routing (user's standing instruction)
- **`task` or the lead:** anything that drives the emulator or the game UI — navigation, scripted input, judging screenshots, multi-step dynamic debugging, running gates. Small models second-guess themselves when the UI misbehaves.
- **`smol` and `tiny`:** pure code tasks only — a 68k routine written against an exact register/memory contract, Python tooling, table generators, static disassembly reading. Their output counts only after the lead or a stronger agent runs a gate in the emulator.
- **Escalate on a stall:** if an agent spends more than about 30 minutes on one bug without new evidence, stop it and fix it yourself or hand it to a stronger model with a precise handoff.
- **`fable`:** deep algorithm/design work (a game-family study, an exact rewrite of a hot routine). Use sparingly.
- After any provider/network error, check which model actually ran. Verify returned work before building on it.

## Task template
Put shared facts in `context`; each task needs a target, the change, and acceptance tests.
- **Read first:** `PLAN.md`, the game's `README.md`, the relevant `work/notes/*.md`, and the skills `amiga-game-speedup`, `amiga-fs-uae-harness`, `amiga-adf-and-hunks`.
- **Exact inputs:** addresses, load base, disk image names, ROM/machine, snapshot names, commands. Never "find the renderer".
- **Allocations:** a code/data address range per agent, checked against `dm` (free RAM map) and the patch tool's map; distinct patch prefixes; distinct `--out` build dirs.
- **Concurrency cap:** at most 2 FS-UAE instances per agent, fewer when several agents run emulators.
- **Rules to state:**
  - "Do NOT spawn subagents."
  - Don't modify game files, `tools/*`, other agents' patches, or `PLAN.md`.
  - Write only your own note and patch files.
- **Evidence contract (verbatim):** every claim cites a disassembly line (address plus text) or raw tool output the agent produced; anything unproven is marked `[INFERENCE]`; paste the raw gate outputs into the final report.
- **Acceptance:** numbered tests with observable outputs (fps numbers, byte-identical frame comparisons, `adf.py diff` output, cold-boot screenshot).

## Shared tools: single owner
`tools/*`, the skills, `PLAN.md` and the per-game README belong to the lead. If an agent hits a tool limit (payload size, debugger quirk, harness bug), it messages the lead: `write agent://<lead>`. The lead changes the tool; the agent works from a private copy meanwhile.

## Verifying returned work (the lead, always)
- Re-run at least one acceptance command yourself: a cold boot, a live input check, an `adf.py diff`, a debugger memory read.
- Spot-check one key static claim with `m68dis` before building on it.
- Known failure modes:
  - **Plausible but wrong claims** ("this steering path is dead code" — disproved by a two-minute live test).
  - **Status lines that overstate** ("validated" that is half true). Insist on pasted tables.
  - **Harness or emulator flakiness reported as game bugs** (black screens from fades or missed clicks; AROS behaviour reported as Kickstart behaviour). Re-run before believing it.
  - **Provider errors.** Check what was left on disk (notes, scratch patches) and relaunch with a summary; don't redo the work.

## Repository etiquette
- The remote is `origin` (GitHub, user-owned). Commit only source, tools, notes and plans; never game disks, ROMs, screenshots or build outputs (see `.gitignore`).
- Run `python3 tools/amigaharness.py roms` before assigning an A1200 task: without Kickstart 3.1 the gate cannot be run, and the task must be scoped to A500/1.3 or to static work.

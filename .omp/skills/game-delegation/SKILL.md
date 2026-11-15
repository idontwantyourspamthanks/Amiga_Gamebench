---
name: game-delegation
description: How to delegate Amiga game reverse-engineering and patching work in gamebench to subagents so the results are trustworthy. Covers model routing, the evidence contract, task template, memory/blob allocation, Copperline session concurrency, provider-failure handling, and the verification the lead must re-run. Use before spawning any task/smol/tiny agent in this project.
---

# Delegating game work to subagents

## Model routing (user's standing instruction)
- **`task` or the lead:** anything that drives the emulator or the game UI — navigation, scripted input, judging screenshots, multi-step dynamic debugging, running gates. Small models second-guess themselves when the UI misbehaves. (The user has set subagents to Sonnet; direct controls were delegated that way successfully.)
- **`smol` and `tiny`:** pure code tasks only — a 68k routine written against an exact register/memory contract, Python tooling, table generators, static disassembly reading. Their output counts only after the lead or a stronger agent runs a gate in the emulator.
- **Escalate on a stall:** if an agent spends more than about 30 minutes on one bug without new evidence, stop it and fix it yourself or hand it to a stronger model with a precise handoff.
- **`fable`:** deep algorithm/design work (a game-family study, an exact rewrite of a hot routine). Use sparingly.
- After any provider/network error, check which model actually ran. Verify returned work before building on it.

## Task template
Put shared facts in `context`; each task needs a target, the change, and acceptance tests.
- **Read first:** `PLAN.md`, the game's `README.md`, the relevant `work/notes/*.md`, and the skills `amiga-game-speedup`, `amiga-copperline`, `amiga-adf-and-hunks`.
- **Exact inputs:** the image (`dist/Amiga_enhanced_games_<date>.hdf`) and game key (`mw2`/`mw2orig`), the harness class (`mw2cl.MW2`), save-state names, commands. Never "find the renderer".
- **Addresses are per-run.** Tell the agent to locate by skeleton in the loaded code hunk (`MW2.locate()` pattern), never to reuse an address from a note.
- **Allocations:** a code/data address range per agent, checked against the live memory map and the patch tool's map; distinct patch prefixes; distinct `--out` build dirs.
- **Concurrency:** each Copperline session is an independent process with its own control port and temp dir, and runs unpaced, so it takes one core while it runs. `[INFERENCE]` that 3-4 at once is fine on a multi-core host: not stress-tested here, and a loaded host cannot change results (emulation is deterministic) but slows wall time. Give each agent its own scratch image (`amigahd.scratch`) and state files; **never let two agents write the shipped image** (Workbench and games write to it).
- **Rules to state:**
  - "Do NOT spawn subagents."
  - Don't modify game files, `tools/*`, other agents' patches, `tests/goldens.json` or `PLAN.md`.
  - Write only your own note and patch files.
- **Evidence contract (verbatim):** every claim cites a disassembly line (address plus text) or raw tool output the agent produced; anything unproven is marked `[INFERENCE]`; paste the raw gate outputs into the final report.
- **Acceptance:** numbered tests with observable outputs (turn values per tick, region/frame hashes, `RESULT` lines, `adf.py diff`, pytest output).

## Shared tools: single owner
`tools/*`, the skills, `PLAN.md`, `tests/conftest.py`, `tests/goldens.json` and the per-game README belong to the lead. If an agent hits a tool limit (payload size, harness bug), it messages the lead: `write agent://<lead>`. The lead changes the tool; the agent works from a private copy meanwhile.

## Verifying returned work (the lead, always)
- Re-run at least one acceptance command yourself: `python3 -m pytest tests/<file> -k <name>`, `tools/test_hd_image.py`, an `adf.py diff`, a `Session` memory read.
- Spot-check one key static claim with `m68dis` before building on it.
- Known failure modes:
  - **Plausible but wrong claims** ("this steering path is dead code" — disproved by a two-minute live test).
  - **Status lines that overstate** ("validated" that is half true). Insist on pasted tables.
  - **Wrong-state measurements:** measuring on a loading screen or a fade. Insist on a region digest or a screenshot proving the state before any number.
  - **Harness misuse reported as game bugs** (wrong coordinate space: `Session.shot` is the 716x285 field, the CLI PNG is 716x540; `mouse_to` on a game cursor; a ROM that is AROS). Re-run before believing it.
  - **Provider errors.** Check what was left on disk (notes, scratch patches) and relaunch with a summary; don't redo the work.
  - **Cached addresses** from an earlier session or build.

## Repository etiquette
- The remote is `origin` (GitHub, user-owned). Commit only source, tools, notes, tests and plans; never game disks, ROMs, screenshots, save states or build outputs (see `.gitignore`; goldens are hashes only).
- Run `python3 -m pytest tests -m "not emu"` before assigning work (seconds) and check `tools/bin/copperline` exists (`tools/fetch_copperline.sh`) and `os/Kickstart/amiga-os-310-a1200.rom` is present: without them the emulator gates cannot be run and the task must be scoped to static work.

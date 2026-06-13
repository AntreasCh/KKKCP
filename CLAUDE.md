# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

It is **also our team's live sync document** for iFX Hack 2026. Read the workflow rules
below — following them is how we avoid git conflicts.

**How we work:** all **5 of us** run **Claude Code individually** on our own machines, one
feature per person. There's **no shared server** — everything runs **locally** (see below).

---

## 🎯 Project

- **Team:** KKKCP
- **Event:** iFX Hack 2026 — 24h hackathon, 13–14 June, University of Limassol (Cyprus)
- **Track:** **Keep Money Safe** (fraud / scams / financial crime / AML / consumer protection)
- **Sponsor:** AWS — using AWS services (Bedrock, Rekognition, Textract, etc.) is a plus.
- **Submission deadline:** **Sun 14 June, 12:00 (noon).** Presentations 14:00–15:30.
- **Repo:** https://github.com/AntreasCh/KKKCP
- **Idea options & decision:** see [`IDEAS.md`](./IDEAS.md)

Judges score on: Innovation & Creativity · Technical Execution · Functionality & Demo ·
Problem Solving · Industry Impact. **Keep a working demo path green at all times.**

---

## 🚦 Git workflow — READ THIS (this is how we avoid conflicts)

Conflicts happen when two people change **the same lines** and push without syncing.
These four habits prevent ~all of them:

**1. Pull before you start working — every time.**
```bash
git pull --rebase origin main
```

**2. Commit small and often.** Small commits = tiny, easy-to-resolve conflicts.
```bash
git add <only-your-files>
git commit -m "clear message about what changed"
```

**3. Pull again right before you push, then push.**
```bash
git pull --rebase origin main   # bring in teammates' work first
git push origin main
```

**4. Own your area.** Don't edit a file someone else is actively working in. Claim files in
the **Team Sync** section below so we don't collide. One feature → one person (or one
branch).

### Editing THIS file (CLAUDE.md) without conflicts
- **Only edit your own block** under *Team Sync*. Never touch a teammate's block.
- **Decision Log** is *append-only*: add a new line at the **top** of the list, never rewrite
  existing lines.
- Commit CLAUDE.md changes on their own (`git commit -m "sync: <your update>"`) and push
  immediately — don't let edits sit.

### If you DO get a conflict (don't panic)
```bash
# After a pull that reports a conflict in <file>:
# 1. Open <file>, find the <<<<<<< ======= >>>>>>> markers.
# 2. Keep both people's work (merge by hand), delete the marker lines.
# 3. Then:
git add <file>
git rebase --continue      # if you were rebasing
git push origin main
```
Stuck? Ping the team before forcing anything. **Never** `git push --force` to `main`.

---

## 🧱 Tech stack & commands

> 🖥️ **Runs locally only — we have no server to host on.** The whole app (and the demo)
> must run on each person's own machine via `localhost`. **Don't** add hosting, deploys, or
> anything that needs a live remote server to demo. Calling cloud **APIs** (e.g. AWS Bedrock)
> from the local app is fine — that's a remote call, not a server we run.

> ⛔ Stack not decided yet — **fill this in the moment we scaffold the project** so the next
> person (or Claude) knows how to run it. Replace the placeholders below.

- **Language / framework:** _TBD_
- **Install deps:** `_TBD_`
- **Run locally (localhost):** `_TBD_`
- **Run tests:** `_TBD_`
- **AWS services in use:** _TBD_

---

## 👥 Team Sync

> Edit **only your own block.** Update "Working on" and "Status" as you go. This is how we
> see who's touching what and avoid stepping on each other. **5 people, 5 blocks** — claim
> a feature/area so two of us never run Claude Code on the same files.

### Andreas Christodoulou (@AntreasCh)
- **Working on:** _________________
- **Files/area owned:** _________________
- **Status:** _________________
- **Blockers:** _________________

### Panayiotis (@pkonto04)
- **Working on:** _________________
- **Files/area owned:** _________________
- **Status:** _________________
- **Blockers:** _________________

### Savvas Kattimeris
- **Working on:** _________________
- **Files/area owned:** _________________
- **Status:** _________________
- **Blockers:** _________________

### (open slot — add your name + block here)
- **Working on:** _________________
- **Files/area owned:** _________________
- **Status:** _________________
- **Blockers:** _________________

### (open slot — add your name + block here)
- **Working on:** _________________
- **Files/area owned:** _________________
- **Status:** _________________
- **Blockers:** _________________

---

## 📋 Decision Log (newest at top — append only)

- _2026-06-13 — Decided: app runs **locally only** (no server to host on); demo runs on localhost. Team of **5**, each running Claude Code individually — one feature/area per person._
- _2026-06-13 — Repo set up; idea options drafted in `IDEAS.md`; awaiting team vote on track idea._

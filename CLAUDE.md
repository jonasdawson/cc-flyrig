# cc-flyrig

**What it is:** a build-time toolkit that scaffolds **typed stdin-JSON command entrypoints** for
Claude Code — hooks and the statusline family (`statusLine` / `subagentStatusLine`) — in the
author's runtime of choice (Python first), generated from a canonical IR of each event family's I/O
shapes. It is the *factory*; the deliverables are native scaffolds.

**How it's organized:** `capture` observes (drives the input + output scenario batteries, records
payloads); `schema` owns the contract lifecycle (the committed IR under `schemas/`, plus
`check`/`seed`/`reconcile`/`diff`); `codegen` transforms the IR into per-runtime scaffolds. `capture`
never writes to `schemas/`.

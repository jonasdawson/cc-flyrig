# cc-flyrig

Write [Claude Code hooks](https://code.claude.com/docs/en/hooks) and the
[statusline](https://code.claude.com/docs/en/statusline) family (`statusLine` /
`subagentStatusLine`) in a language you're already comfortable in, and skip the fiddly parts.
This repo ships ready-made, **typed stdin-JSON command entrypoints**: each event family's input (and,
where it has one, output) is already modeled, stdin → handler → stdout is already wired, and you
just copy one into your project and fill in a single `handle()` function.

Python and TypeScript scaffolds for both hooks and the statusline family are ready to use — the
latest version (normally the latest one or two) is committed directly under
[scaffolds/python](scaffolds/python) and its TypeScript counterpart under
[scaffolds/typescript](scaffolds/typescript), as well as being
available as a [GitHub Release](#generating-scaffolds-for-a-claude-code-version-that-isnt-in-the-repo)
archive. This initial public release ships a single-version snapshot, `2.1.201`; future releases
resume refreshing that window with each new Claude Code version.

## Quick start

The Quick Start below uses the versions committed directly in the repo, one folder per event per
language, under `scaffolds/<language>/cc-<version>/` — there's nothing to install or generate.
Whatever your language, the process is the same:

1. **Copy** the folder for your event out of `scaffolds/<language>/cc-<version>/`. Each one has two
   files: a generated `_harness` (the types + plumbing — don't edit) and the entrypoint you fill in.
   Where you put it is up to you (e.g. `.claude/hooks/` for hooks, `.claude/status_line/` for status line customizations).
2. **Fill in `handle()`** in the entrypoint. The event is already typed, so your editor autocompletes
   every field; return a decision or return nothing.
3. **Set up the runtime and wire it into `settings.json`** — this part is language-specific
   (interpreter, dependencies, the exact command).

Step 3 is where languages differ, so each ships its own short Quick Start with copy-paste commands:

| Language | Quick Start | Notes |
| --- | --- | --- |
| **Python** | [scaffolds/python/README.md](scaffolds/python/README.md) | 3.10+, stdlib-only — no packages to install. |
| **TypeScript** | [scaffolds/typescript/README.md](scaffolds/typescript/README.md) | Node, runs via `tsx`. |
| Go, JavaScript, bash, … | _coming by contribution_ | See [CONTRIBUTING.md](CONTRIBUTING.md). |

Every file is stamped with the Claude Code version it was generated from, so when you upgrade Claude
Code, re-copy the matching folder and you're back in sync.

## Generating scaffolds for a Claude Code version that isn't in the repo

The repo ships scaffolds for specific Claude Code versions (run `ls scaffolds/python` to see which).
Hook payloads rarely change between releases, so if your version isn't listed, **the newest committed
scaffold almost certainly still matches**. In all likelihood, the Quick Start works as-is, and the only difference is
the version stamp.

If you need scaffolds stamped for your exact version, download the GitHub Release (no tooling
required). Every `cc-<version>` tag has a matching GitHub Release with pre-built archives for each
runtime:

```sh
# Download and extract the Python scaffold archive for your version
gh release download cc-<your-version> --pattern 'python-cc-<your-version>.tar.gz'
tar xzf python-cc-<your-version>.tar.gz
```

Copy the event folder you want into `.claude/hooks/` as in the Quick Start.

> Building from source instead, or verifying the shortcut still matches your exact version? See
> [CONTRIBUTING.md](CONTRIBUTING.md).

## Why this exists

A Claude Code hook is just a script that Claude Code calls: it gets an event as JSON on stdin, does
something, and (optionally) writes a decision as JSON to stdout. Simple in theory. In practice, two
things slow you down:

- **The same boilerplate, every single time.** Read stdin, parse the right shape, branch on it, build
  a valid decision, set the correct exit code — all before you write a line of your actual logic.
- **The exact JSON shape is hard to pin down.** The official hooks docs and the in-app `/hooks` menu
  are genuinely useful, but the fields are split across different sections and can be a bit hard to follow. Additionally, in some places they don't quite match the
  JSON Claude Code actually sends and accepts. Claude Code does a decent job of building these hooks or statusline files with its configuration skills if you ask it to, but I personally had mixed success with this.

My hope is for this repo to make things easier for people who want to understand and build hooks or customize their statusline. It maintains a canonical, versioned schema of every hook event's real
input and output checked against payloads captured from a live Claude Code, and generates typed
models straight from it. You get correct types and zero plumbing, so you can spend your time on the
part that's actually yours: what the hook *does*. Furthermore, by providing the scaffolded `_harness` files generated by this repo as context to Claude, building hooks and statuslines becomes *significantly* easier and more reliable with the benefit of clear type definitions.

What you scaffold is **your own code**, and it stays light:

- **Inline models, no third-party packages.** The types are vendored right into your file — no
  libraries to `pip install` or `npm install`. Python runs on the standard library alone; TypeScript
  needs only a TS runner (`tsx`) to execute it.
- **The full skeleton.** stdin → typed event → your `handle()` → typed decision → stdout, with exit
  codes already correct.
- **A version stamp**, so you can tell when a scaffold has gone stale.

### What it deliberately does *not* do

It's up to you to setup your `settings.json` and wire up the hook. Reference the
[official settings schema](https://code.claude.com/docs/en/hooks) for autocomplete.

## Supported languages

| Runtime | Status | Notes |
| --- | --- | --- |
| **Python** | Supported | 3.10+, stdlib-only (`@dataclass`, `X \| None` unions, `json`); inline models. |
| **TypeScript** | Supported | Node, dependency-light (`interface` + string-literal unions, `parse`/`serialize`, `node:fs`). |
| Go, JavaScript, bash, … | Pending |  |

Want your language? Adding one is contributing templates, not changing the engine. see
[CONTRIBUTING.md](CONTRIBUTING.md) for a worked example (TypeScript).

## Learn more

| Document | What it covers |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to add support for a new language. |
| [capture_harness/README.md](capture_harness/README.md) | Runbook for capturing live payloads from a real Claude Code (battery definitions + in-session assets; the CLI lives in `src/`) — runnable by a contributor, reviewed by a maintainer. |
| [`src/cc_flyrig/schema/`](src/cc_flyrig/schema/) | The contract lifecycle: `schema check` validates committed captures against the committed schema, `schema seed` forward-copies a schema into a new CC version, `schema reconcile` proposes additive schema properties from captures, `schema diff` shows what changed between two committed schema versions. |

> **Working on the project itself?** It runs from this repo as `python -m cc_flyrig.*`
> modules: `capture` drives the batteries and records payloads (never writes to `schemas/`), `schema`
> owns the schema lifecycle (`check`/`seed`/`reconcile`/`diff`), and `codegen` generates the
> scaffolds. Start with the [capture harness runbook](capture_harness/README.md).

---

Last updated: 2026-07-04

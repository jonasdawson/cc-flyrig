# TypeScript hook scaffolds — Quick Start

Typed, dependency-light Claude Code hook entrypoints for Node. Each folder under `cc-<version>/` is one
hook event: copy it into your project, fill in `handle()`, and point `settings.json` at it. The models
are vendored right into the file — the only thing you install is a TypeScript runner.

> New to the toolkit? The [top-level README](../../README.md) explains what these scaffolds are and
> why the types are generated from a captured schema rather than hand-written.

## 1. Copy a scaffold into your project

Pick your event from a `cc-<version>/` folder and copy it into your project's `.claude/hooks/`:

```sh
mkdir -p .claude/hooks
cp -r path/to/cc-flyrig/scaffolds/typescript/cc-2.1.201/pre_tool_use .claude/hooks/pre_tool_use
```

Each folder has exactly two files:

| File | What it is |
| --- | --- |
| `_harness.ts` | Generated `interface`s + the stdin → `handle()` → stdout plumbing and exit codes. **Don't edit.** |
| `index.ts` | The entrypoint. **This is where you work.** |

All 30 events are available (`pre_tool_use`, `post_tool_use`, `session_start`, …), and you can copy in
as many as you like.

## 2. Fill in `handle()`

Open `index.ts`. The event is already typed, so your editor autocompletes every field. Return a
decision, or return `null` to stay out of the way.

```typescript
// .claude/hooks/pre_tool_use/index.ts
function handle(event: PreToolUseInput): PreToolUseOutput | null {
  if (event.toolName === "Write" && String(event.toolInput.file_path ?? "").includes("/secrets/")) {
    return {
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: "writes to /secrets/ are blocked",
      },
    };
  }
  return null; // do nothing — let the tool call through
}
```

Fields are camelCase in TypeScript (`toolName`, `toolInput`); the harness maps them to/from the
verbatim wire keys for you. `toolInput` is a `Record<string, unknown>`, so coerce values you read from
it (e.g. `String(...)`) before using them.

## 3. Set up the runtime

Claude Code runs your hook as a separate, non-interactive process — it does **not** inherit your
shell. You need [`tsx`](https://tsx.is) to run the `.ts` file directly. The Node equivalent of a
virtual environment is a local `node_modules`: install `tsx` into your project so it's always present,
rather than letting `npx` fetch it over the network on every cold start.

```sh
npm init -y          # if you don't already have a package.json
npm install -D tsx
```

## 4. Wire it into `settings.json`

Run the entry file with `tsx`. The command runs from your project root:

```json
{
  "hooks": {
    "PreToolUse": [
      { "type": "command", "command": "npx tsx .claude/hooks/pre_tool_use/index.ts" }
    ]
  }
}
```

`npx` uses the `tsx` from your local `node_modules` when it's installed. That's the whole loop.

## Keeping current

`VERSION` records the newest Claude Code version generated here, and each scaffold is stamped with the
version it was cut from. When you upgrade Claude Code, re-copy the matching `cc-<version>/` folder so
your types stay in sync. If your exact version isn't committed yet, older versions are available as
pre-built archives in the matching `cc-<version>` GitHub Release; see
[Generating scaffolds for a version that isn't in the repo](../../README.md#generating-scaffolds-for-a-claude-code-version-that-isnt-in-the-repo)
for both paths.

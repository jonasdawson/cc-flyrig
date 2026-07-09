# Python hook scaffolds — Quick Start

Typed, **stdlib-only** Claude Code hook entrypoints for Python 3.10+. Each folder under
`cc-<version>/` is one hook event: copy it into your project, fill in `handle()`, and point
`settings.json` at it. No packages to install — the models are vendored right into the file.

> New to the toolkit? The [top-level README](../../README.md) explains what these scaffolds are and
> why the types are generated from a captured schema rather than hand-written.

## 1. Copy a scaffold into your project

Pick your event from a `cc-<version>/` folder (newest version wins unless you need to pin an older
one) and copy it into your project's `.claude/hooks/`:

```sh
mkdir -p .claude/hooks
cp -r path/to/cc-flyrig/scaffolds/python/cc-2.1.201/pre_tool_use .claude/hooks/pre_tool_use
```

Each folder has exactly two files:

| File | What it is |
| --- | --- |
| `_harness.py` | Generated `@dataclass` models + the stdin → `handle()` → stdout plumbing and exit codes. **Don't edit.** |
| `__main__.py` | The entrypoint. **This is where you work.** |

All 30 events are available (`pre_tool_use`, `post_tool_use`, `session_start`, …), and you can copy in
as many as you like.

## 2. Fill in `handle()`

Open `__main__.py`. The event is already typed, so your editor autocompletes every field. Return a
decision, or return `None` to stay out of the way.

```python
# .claude/hooks/pre_tool_use/__main__.py
def handle(event: PreToolUseInput) -> PreToolUseOutput | None:
    if event.tool_name == "Write" and "/secrets/" in (event.tool_input.get("file_path") or ""):
        return PreToolUseOutput(
            hook_specific_output=PreToolUseHookSpecificOutput(
                hook_event_name="PreToolUse",
                permission_decision="deny",
                permission_decision_reason="writes to /secrets/ are blocked",
            )
        )
    return None  # do nothing — let the tool call through
```

## 3. Set up the runtime

Claude Code runs your hook as a separate, non-interactive process — it does **not** inherit your
shell, so a venv you "activated" in a terminal won't be picked up. Because the scaffolds are
stdlib-only there's nothing to `pip install`; you just need to make sure a Python 3.10+ runs, and name
it explicitly in the command (step 4).

A virtual environment is the clean way to pin which interpreter that is:

```sh
python3 -m venv .claude/hooks/.venv   # isolated interpreter; nothing to install into it
```

If you skip the venv, the system `python3` works too, as long as it's 3.10+.

## 4. Wire it into `settings.json`

Invoke the folder as a module. `PYTHONPATH` tells Python where to find it — `.claude` isn't a valid
package name, so you point at its parent (`.claude/hooks`). The command runs from your project root:

```json
{
  "hooks": {
    "PreToolUse": [
      { "type": "command", "command": "PYTHONPATH=.claude/hooks python3 -m pre_tool_use" }
    ]
  }
}
```

Using the venv from step 3? Name its interpreter instead of `python3`:

```json
{ "type": "command", "command": "PYTHONPATH=.claude/hooks .claude/hooks/.venv/bin/python -m pre_tool_use" }
```

> The `VAR=value command` prefix is POSIX-shell syntax (macOS/Linux). On Windows, set `PYTHONPATH` via
> the hook's environment or a wrapper script instead.

That's the whole loop.

## Keeping current

`VERSION` records the newest Claude Code version generated here, and each scaffold is stamped with the
version it was cut from. When you upgrade Claude Code, re-copy the matching `cc-<version>/` folder so
your types stay in sync. If your exact version isn't committed yet, older versions are available as
pre-built archives in the matching `cc-<version>` GitHub Release; see
[Generating scaffolds for a version that isn't in the repo](../../README.md#generating-scaffolds-for-a-claude-code-version-that-isnt-in-the-repo)
for both paths.

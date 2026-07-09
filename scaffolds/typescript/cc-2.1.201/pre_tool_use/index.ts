// Edit handle() with your hook logic.
// Wire into settings.json: { "PreToolUse": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PreToolUseInput, PreToolUseOutput, run } from "./_harness";

function handle(event: PreToolUseInput): PreToolUseOutput | null {
  // Decide what to do with this PreToolUse event.
  // Return a PreToolUseOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

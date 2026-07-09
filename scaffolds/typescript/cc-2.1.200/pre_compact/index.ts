// Edit handle() with your hook logic.
// Wire into settings.json: { "PreCompact": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PreCompactInput, PreCompactOutput, run } from "./_harness";

function handle(event: PreCompactInput): PreCompactOutput | null {
  // Decide what to do with this PreCompact event.
  // Return a PreCompactOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

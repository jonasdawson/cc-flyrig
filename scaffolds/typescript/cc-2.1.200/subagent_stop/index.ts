// Edit handle() with your hook logic.
// Wire into settings.json: { "SubagentStop": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { SubagentStopInput, SubagentStopOutput, run } from "./_harness";

function handle(event: SubagentStopInput): SubagentStopOutput | null {
  // Decide what to do with this SubagentStop event.
  // Return a SubagentStopOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

// Edit handle() with your hook logic.
// Wire into settings.json: { "SubagentStart": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { SubagentStartInput, SubagentStartOutput, run } from "./_harness";

function handle(event: SubagentStartInput): SubagentStartOutput | null {
  // Decide what to do with this SubagentStart event.
  // Return a SubagentStartOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

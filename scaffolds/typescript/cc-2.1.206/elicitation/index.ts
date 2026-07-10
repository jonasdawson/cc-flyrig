// Edit handle() with your hook logic.
// Wire into settings.json: { "Elicitation": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { ElicitationInput, ElicitationOutput, run } from "./_harness";

function handle(event: ElicitationInput): ElicitationOutput | null {
  // Decide what to do with this Elicitation event.
  // Return a ElicitationOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

// Edit handle() with your hook logic.
// Wire into settings.json: { "ElicitationResult": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { ElicitationResultInput, ElicitationResultOutput, run } from "./_harness";

function handle(event: ElicitationResultInput): ElicitationResultOutput | null {
  // Decide what to do with this ElicitationResult event.
  // Return a ElicitationResultOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

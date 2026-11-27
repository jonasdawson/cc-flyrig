// Edit handle() with your hook logic.
// Wire into settings.json: { "StopFailure": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { StopFailureInput, run } from "./_harness";

function handle(event: StopFailureInput): void {
  // React to this StopFailure event. Fill in your logic.
  throw new Error("Not implemented");
}

run(handle);

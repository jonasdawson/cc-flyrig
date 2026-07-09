// Edit handle() with your hook logic.
// Wire into settings.json: { "SessionEnd": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { SessionEndInput, run } from "./_harness";

function handle(event: SessionEndInput): void {
  // React to this SessionEnd event. Fill in your logic.
  throw new Error("Not implemented");
}

run(handle);

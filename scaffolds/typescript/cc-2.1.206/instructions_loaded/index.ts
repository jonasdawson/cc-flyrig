// Edit handle() with your hook logic.
// Wire into settings.json: { "InstructionsLoaded": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { InstructionsLoadedInput, run } from "./_harness";

function handle(event: InstructionsLoadedInput): void {
  // React to this InstructionsLoaded event. Fill in your logic.
  throw new Error("Not implemented");
}

run(handle);

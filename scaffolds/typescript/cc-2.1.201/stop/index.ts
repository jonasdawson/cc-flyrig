// Edit handle() with your hook logic.
// Wire into settings.json: { "Stop": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { StopInput, StopOutput, run } from "./_harness";

function handle(event: StopInput): StopOutput | null {
  // Decide what to do with this Stop event.
  // Return a StopOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

// Edit handle() with your hook logic.
// Wire into settings.json: { "PreModelSwitch": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PreModelSwitchInput, PreModelSwitchOutput, run } from "./_harness";

function handle(event: PreModelSwitchInput): PreModelSwitchOutput | null {
  // Decide what to do with this PreModelSwitch event.
  // Return a PreModelSwitchOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

// Edit handle() with your hook logic.
// Wire into settings.json: { "TeammateIdle": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { TeammateIdleInput, TeammateIdleOutput, run } from "./_harness";

function handle(event: TeammateIdleInput): TeammateIdleOutput | null {
  // Decide what to do with this TeammateIdle event.
  // Return a TeammateIdleOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

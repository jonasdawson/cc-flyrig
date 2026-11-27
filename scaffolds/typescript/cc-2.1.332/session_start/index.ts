// Edit handle() with your hook logic.
// Wire into settings.json: { "SessionStart": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { SessionStartInput, SessionStartOutput, run } from "./_harness";

function handle(event: SessionStartInput): SessionStartOutput | null {
  // Decide what to do with this SessionStart event.
  // Return a SessionStartOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

// Edit handle() with your hook logic.
// Wire into settings.json: { "CwdChanged": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { CwdChangedInput, CwdChangedOutput, run } from "./_harness";

function handle(event: CwdChangedInput): CwdChangedOutput | null {
  // Decide what to do with this CwdChanged event.
  // Return a CwdChangedOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

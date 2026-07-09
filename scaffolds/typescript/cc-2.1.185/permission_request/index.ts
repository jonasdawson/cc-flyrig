// Edit handle() with your hook logic.
// Wire into settings.json: { "PermissionRequest": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PermissionRequestInput, PermissionRequestOutput, run } from "./_harness";

function handle(event: PermissionRequestInput): PermissionRequestOutput | null {
  // Decide what to do with this PermissionRequest event.
  // Return a PermissionRequestOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

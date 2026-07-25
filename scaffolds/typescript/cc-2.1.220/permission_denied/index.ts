// Edit handle() with your hook logic.
// Wire into settings.json: { "PermissionDenied": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PermissionDeniedInput, PermissionDeniedOutput, run } from "./_harness";

function handle(event: PermissionDeniedInput): PermissionDeniedOutput | null {
  // Decide what to do with this PermissionDenied event.
  // Return a PermissionDeniedOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

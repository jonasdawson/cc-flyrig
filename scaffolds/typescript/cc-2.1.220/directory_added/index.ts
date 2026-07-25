// Edit handle() with your hook logic.
// Wire into settings.json: { "DirectoryAdded": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { DirectoryAddedInput, run } from "./_harness";

function handle(event: DirectoryAddedInput): void {
  // React to this DirectoryAdded event. Fill in your logic.
  throw new Error("Not implemented");
}

run(handle);

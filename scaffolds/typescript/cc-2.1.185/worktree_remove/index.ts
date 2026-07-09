// Edit handle() with your hook logic.
// Wire into settings.json: { "WorktreeRemove": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { WorktreeRemoveInput, run } from "./_harness";

function handle(event: WorktreeRemoveInput): void {
  // React to this WorktreeRemove event. Fill in your logic.
  throw new Error("Not implemented");
}

run(handle);

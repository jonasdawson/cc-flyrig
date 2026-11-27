// Edit handle() with your hook logic.
// Wire into settings.json: { "WorktreeCreate": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { WorktreeCreateInput, WorktreeCreateOutput, run } from "./_harness";

function handle(event: WorktreeCreateInput): WorktreeCreateOutput | null {
  // Decide what to do with this WorktreeCreate event.
  // Return a WorktreeCreateOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

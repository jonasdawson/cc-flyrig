// Edit handle() with your hook logic.
// Wire into settings.json: { "TaskCompleted": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { TaskCompletedInput, TaskCompletedOutput, run } from "./_harness";

function handle(event: TaskCompletedInput): TaskCompletedOutput | null {
  // Decide what to do with this TaskCompleted event.
  // Return a TaskCompletedOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

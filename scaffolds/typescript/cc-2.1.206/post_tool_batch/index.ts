// Edit handle() with your hook logic.
// Wire into settings.json: { "PostToolBatch": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PostToolBatchInput, PostToolBatchOutput, run } from "./_harness";

function handle(event: PostToolBatchInput): PostToolBatchOutput | null {
  // Decide what to do with this PostToolBatch event.
  // Return a PostToolBatchOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

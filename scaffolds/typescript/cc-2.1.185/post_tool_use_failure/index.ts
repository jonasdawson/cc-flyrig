// Edit handle() with your hook logic.
// Wire into settings.json: { "PostToolUseFailure": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PostToolUseFailureInput, PostToolUseFailureOutput, run } from "./_harness";

function handle(event: PostToolUseFailureInput): PostToolUseFailureOutput | null {
  // Decide what to do with this PostToolUseFailure event.
  // Return a PostToolUseFailureOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

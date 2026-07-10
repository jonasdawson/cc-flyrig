// Edit handle() with your hook logic.
// Wire into settings.json: { "PostToolUse": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PostToolUseInput, PostToolUseOutput, run } from "./_harness";

function handle(event: PostToolUseInput): PostToolUseOutput | null {
  // Decide what to do with this PostToolUse event.
  // Return a PostToolUseOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

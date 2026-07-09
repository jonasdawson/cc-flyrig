// Edit handle() with your hook logic.
// Wire into settings.json: { "UserPromptExpansion": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { UserPromptExpansionInput, UserPromptExpansionOutput, run } from "./_harness";

function handle(event: UserPromptExpansionInput): UserPromptExpansionOutput | null {
  // Decide what to do with this UserPromptExpansion event.
  // Return a UserPromptExpansionOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

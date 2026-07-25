// Edit handle() with your hook logic.
// Wire into settings.json: { "UserPromptSubmit": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { UserPromptSubmitInput, UserPromptSubmitOutput, run } from "./_harness";

function handle(event: UserPromptSubmitInput): UserPromptSubmitOutput | null {
  // Decide what to do with this UserPromptSubmit event.
  // Return a UserPromptSubmitOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

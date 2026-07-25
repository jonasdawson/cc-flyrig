// Edit handle() with your hook logic.
// Wire into settings.json: { "MessageDisplay": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { MessageDisplayInput, MessageDisplayOutput, run } from "./_harness";

function handle(event: MessageDisplayInput): MessageDisplayOutput | null {
  // Decide what to do with this MessageDisplay event.
  // Return a MessageDisplayOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

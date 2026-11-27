// Edit handle() with your hook logic.
// Wire into settings.json: { "PostModelSwitch": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PostModelSwitchInput, PostModelSwitchOutput, run } from "./_harness";

function handle(event: PostModelSwitchInput): PostModelSwitchOutput | null {
  // Decide what to do with this PostModelSwitch event.
  // Return a PostModelSwitchOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

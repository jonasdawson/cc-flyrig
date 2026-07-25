// Edit handle() with your hook logic.
// Wire into settings.json: { "PostCompact": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PostCompactInput, run } from "./_harness";

function handle(event: PostCompactInput): void {
  // React to this PostCompact event. Fill in your logic.
  throw new Error("Not implemented");
}

run(handle);

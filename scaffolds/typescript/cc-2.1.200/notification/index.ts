// Edit handle() with your hook logic.
// Wire into settings.json: { "Notification": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { NotificationInput, run } from "./_harness";

function handle(event: NotificationInput): void {
  // React to this Notification event. Fill in your logic.
  throw new Error("Not implemented");
}

run(handle);

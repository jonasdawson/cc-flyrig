// Edit handle() with your logic.
// Wire into settings.json (a single command, not a hook array): { "statusLine": { "type": "command", "command": "npx tsx <path>/index.ts" } }

import { StatusLineData, run } from "./_harness";

function handle(event: StatusLineData): string {
  // Return the status line text for this StatusLine event.
  throw new Error("Not implemented");
}

run(handle);

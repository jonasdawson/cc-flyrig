// Edit handle() with your logic.
// Wire into settings.json (a single command, not a hook array): { "subagentStatusLine": { "type": "command", "command": "npx tsx <path>/index.ts" } }

import { SubagentStatusLineInput, SubagentStatusLineOutput, run } from "./_harness";

function handle(event: SubagentStatusLineInput): SubagentStatusLineOutput[] {
  // Return one SubagentStatusLineOutput row per visible subagent for this SubagentStatusLine event.
  throw new Error("Not implemented");
}

run(handle);

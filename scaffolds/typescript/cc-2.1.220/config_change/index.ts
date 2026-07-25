// Edit handle() with your hook logic.
// Wire into settings.json: { "ConfigChange": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { ConfigChangeInput, ConfigChangeOutput, run } from "./_harness";

function handle(event: ConfigChangeInput): ConfigChangeOutput | null {
  // Decide what to do with this ConfigChange event.
  // Return a ConfigChangeOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

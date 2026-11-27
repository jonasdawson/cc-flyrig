// Edit handle() with your hook logic.
// Wire into settings.json: { "PreSkillShellCommand": [{ "type": "command", "command": "npx tsx <path>/index.ts" }] }

import { PreSkillShellCommandInput, PreSkillShellCommandOutput, run } from "./_harness";

function handle(event: PreSkillShellCommandInput): PreSkillShellCommandOutput | null {
  // Decide what to do with this PreSkillShellCommand event.
  // Return a PreSkillShellCommandOutput to issue a decision, or null to defer to other hooks.
  throw new Error("Not implemented");
}

run(handle);

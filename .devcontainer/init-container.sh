#!/bin/bash
set -euo pipefail

# Git identity — set GIT_USER_NAME / GIT_USER_EMAIL in your environment or in
# devcontainer.json's containerEnv (they are forwarded from the host via localEnv).
if [ -n "${GIT_USER_NAME:-}" ]; then
  git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "${GIT_USER_EMAIL:-}" ]; then
  git config --global user.email "$GIT_USER_EMAIL"
fi

# Seed user-level Claude config from the read-only host bind mount
cp /tmp/host-claude/settings.json ~/.claude/settings.json 2>/dev/null || echo '{}' > ~/.claude/settings.json

# Override permissions to allow all tool calls without prompts.
# The firewall (init-firewall.sh) is the security boundary in this container, not the permission system.
jq '.permissions.allow = ["Bash(*)", "Edit", "Write", "MultiEdit", "WebFetch(*)", "WebSearch(*)"]' \
  ~/.claude/settings.json > /tmp/cc-settings.json && mv /tmp/cc-settings.json ~/.claude/settings.json

# esbuild gates TypeScript generation (cli/esbuild.py); tsc/tsx also live here for tests + release.
npm ci

# Run user-local overrides if present (gitignored — see init-user.sh.example for a template).
if [ -f ".devcontainer/init-user.sh" ]; then
  # shellcheck source=/dev/null
  source ".devcontainer/init-user.sh"
fi

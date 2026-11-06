# Distribution and versioning

## Installed application
- The repository source has this skill at `.agents/skills/tidmunz-remote-operator/SKILL.md` with its references.
- The desktop launcher on a *new* PC installs the published GitHub **Release** source archive, including this directory.
- The in-app updater installs the Release asset `tidmun-studio-patch.zip`. Its build script includes all `.agents/skills/**/*.md`; the updater verifies the manifest's SHA-256 entries and installs new skill files alongside code.
- Updating GitHub `main` alone does **not** update customers' installed programs. A deliberately published version/tag and an app update are still required.
- The Release also publishes `tidmunz-operator-skill.zip` for import into other skills-compatible agents. The skill can be extracted without installing the Windows app.

## In another GPT or account
Provide the ZIP or skill directory through the other assistant's supported import/knowledge mechanism. The assistant must read `SKILL.md` and reference files and connect an explicitly authorized computer-access tool; the skill does not grant access or install a plugin by itself. Keep secrets and personal tokens separate from every shared skill.

## Source of truth
Maintain the content in GitHub source; sync changes through a reviewed versioned commit and a Release when requested. Do not overwrite customer-modified files outside the release-owned skill directory. Local project data, GPT conversations, paid receipts, configs and credentials must never ship in packages.

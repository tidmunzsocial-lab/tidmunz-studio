# Distribution and versioning

## Current status — GitHub source only
- The repository source has this skill at `.agents/skills/tidmunz-remote-operator/SKILL.md` with its references.
- This skill is in GitHub for evaluation. The released installer has not been configured to distribute it automatically.
- The in-app updater currently does **not** add skill Markdown files to its patch. Do not promise installation until that feature is tested and explicitly authorized.
- Updating GitHub `main` alone does **not** update customers' installed programs. A deliberately published version/tag and an app update are still required.
- `tools/build_operator_skill.py` can build a standalone `tidmunz-operator-skill.zip` locally, but the Release workflow does not yet publish that asset.

## In another GPT or account
Provide the ZIP or skill directory through the other assistant's supported import/knowledge mechanism. The assistant must read `SKILL.md` and reference files and connect an explicitly authorized computer-access tool; the skill does not grant access or install a plugin by itself. Keep secrets and personal tokens separate from every shared skill.

## Source of truth
Maintain the content in GitHub source; sync changes through a reviewed versioned commit and a Release when requested. Do not overwrite customer-modified files outside the release-owned skill directory. Local project data, GPT conversations, paid receipts, configs and credentials must never ship in packages.

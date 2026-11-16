---
name: tidmunz-plugin-source-fidelity
description: Build or revise the ChatGPT Tidmunz Studio AI Operator plugin from its canonical GitHub skills with maximal semantic and inventory fidelity, preserving source rules and verifying differences before releasing.
---

# Tidmunz AI Operator — GitHub-to-plugin fidelity rule

## Canonical source

Use the intended repository tidmunzsocial-lab/tidmunz-studio at plugins/tidmunz-studio-ai-operator on the selected branch (normally main) as the source of truth for its skill catalog. Fetch skills/catalog.json first, then the full SKILL.md for every catalog entry when building or updating the plugin. Do not rely on prior-chat summaries, guessed file lists, old embedded instructions or a bare version number.

A plugin may be reconstructed from understanding GitHub rather than copied byte for byte, but its behavior, mandatory constraints, stop conditions, prerequisites, known limitations, safety guarantees and skill inventory must match the source as closely as possible. Favor preserving the original skill text and verified references when packaging allows. Do not paraphrase away mandatory conditions, invert defaults, invent capabilities or silently omit skills.

## Rebuild and review checklist

1. Record repo, branch, source commit SHA, catalog version, each skill name/path and content SHA or equivalent fingerprint.
2. Compare the source catalog to the package's actual skill list and metadata. Flag all missing or extra skills, changed safety rules and altered operational steps; explain deliberate transformations in a concise diff or checklist.
3. Adapt to ChatGPT-specific packaging and tool capabilities without promising persistent model execution, background reasoning or machine access that the connected connector does not supply.
4. Pay particular attention to tidmunz-chrome-followup, tidmunz-device-routing, tidmunz-auto-workflow, tidmunz-auto-supervision, and the hard stop at the human sound-effect chooser. The extension is a distinct component from the bot plugin and native Video Auto.
5. Resolve conflicts using the latest explicit user scope and current verified app implementation. Escalate high-impact unresolved conflicts instead of erasing source requirements or choosing an arbitrary historical rule.
6. Verify the packaged plugin in the release/install context: inspect every included skill path and critical guidance. Equal version strings alone do not prove parity. A GitHub commit is NOT an installed plugin release.
7. Only publish or update an owned plugin when authorized using the actual plugin-editing mechanism; read it back afterward. Do not rebuild other users' plugins, change permissions, publish a software release or auto-install an app simply because the catalog was read.

Never embed personal devices, user-specific remote URLs, access tokens, emails, private project files or receipts in reusable skills. Preserve unrelated prior behavior.

## Acceptance condition

Report separately GitHub source updated, plugin package rebuilt, plugin release published, and installed plugin verified. Mark a stage complete only after direct evidence; otherwise name the pending stage.

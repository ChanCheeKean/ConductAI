---
name: "memory-hygiene"
description: "Verify a retrieved memory note against the governing source before trusting it, and keep memory current"
routes: ["cli_script_root_cause", "cli_prescreened_assurance"]
version: "1.0"
---
# Verify memory against the current governing source

1. Treat every retrieved memory note as a lead to reverify, never as evidence by itself, regardless of confidence, access count, or how many prior observations it consolidates.
2. Resolve the governing policy, glossary, or script version as of the interaction date and compare it against the note's recorded basis version.
3. When the note's basis is stale, supersede it: close its valid-to at the date the governing source changed, and cite the new governing source in the replacement.
4. When at least three compatible observations exist, consolidate them into one sourced note and archive the inputs rather than leaving duplicates active.
5. Never write a memory note about an individual colleague's fault when the attribution counterfactual shows a script, system, or supervisor material caused the same outcome for any colleague who followed it.

Stop once the note's status (kept, superseded, or consolidated) is settled against the current governing source, not the source the note was originally written against.

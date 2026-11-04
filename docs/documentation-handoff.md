# Historical Backend Documentation Handoff

This page preserves the original documentation handoff. References to local pages,
feature branches and pending publication below describe that task, not the current
repository status. Maintained handbook links now use `main`; tutorial evidence
keeps its recorded commits. Current installation starts at
[Install the CLI](../README.md#install-the-cli).

This is a documentation-only package on the agreed feature branch. No product API,
schema JSON, dependency pin or target implementation is changed here.

Run `node --test scripts/check-docs.test.mjs` and `node scripts/check-docs.mjs`
with Node 24. CI runs those checks without a frontend or sample checkout.

Read the [central handoff](https://github.com/oraylis/datam8/blob/main/docs/handoff.md) for branch/workspace mapping,
results and manual merge order. The new central and component pages are local until
their branches are published. After manual merges, update development links to main;
keep tutorial evidence bound to commits. Public user workflows belong in the handbook.

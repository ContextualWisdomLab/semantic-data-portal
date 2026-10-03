# SDP self-hosted CI migration

The user's October 3, 2026 instruction is to move this workstream's CI entirely to self-hosted runners. All four existing SDP jobs now request `self-hosted`, `linux`, `x64`, `cwlab-ci-isolated`. Job names, Python 3.12 and Atheris constraints, hash-locked installation, schedule, artifacts and token permissions remain unchanged.

This is a staged source change, not verified runtime activation. No registered runner carried `cwlab-ci-isolated` in the preparation API read. The operator must supply disposable Ubuntu 24.04-compatible Linux x64 machines, clang/libFuzzer, Python action prerequisites and isolation from privileged control hosts, production networks and long-lived secrets. Rebuild the execution environment after each job; do not add this label to an existing privileged host solely to release the queue. Trusted secret-bearing jobs and untrusted PR execution require separate clean instances. A label does not attest isolation.

The central `.github` migration covers organization-required workflows separately. This product branch is stacked on the existing PR107 source without altering PR107 or PR82 branches. Product tests remain separate from protected-main shipment and real runner acceptance. Keep this proposal Draft until isolated capacity and successful canary evidence exist; then require fresh exact-head checks and eligible independent approval before normal merge. Do not start issue108 before PR82 and PR107 merge.

References: GitHub Docs, “Using self-hosted runners in a workflow” and “Secure use reference” (retrieved October 3, 2026). Central detailed routing contract: `docs/doctoring/all-self-hosted-runner-routing-20261003.md` in the matching central migration branch.

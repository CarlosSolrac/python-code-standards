Plan to upgrade all packages

Plan a CI pipeline to automatically upgrade packages and run test suite

Suggest a memory cleanup: which TODOs to remove from Claude memory

Evaluate TY, PYRE, PYREFLY

Create a /prep-nightshift skill (user-invoked, beside nightshift/) that readies a repository for a /nightshift run, as done by hand on 2026-10-16: check that the default branch matches origin, gh is logged in, Codex answers, and the session's permission mode will not prompt; collect the tasks nightshift would pick up (TODO.md, plan files, issues) and show them to the user to confirm scope; find inputs the task worktrees would miss because they branch from origin/<default> (untracked or unpushed files, plans that live only in the conversation) and write them to a plan file under docs/plans/ with the decisions already made; flag every task step outside nightshift's authority (dependencies, CI, hooks, build config, anything outside the repository) and offer to do it in daytime first or let it end blocked; list the morning steps; commit and push the prepared files only after the user approves.



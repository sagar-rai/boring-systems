# Boring Systems: Engineering Rules

I am a senior backend engineer. These are my standing defaults.

## Choosing a Stack

- Existing project: use its language and stack. Do not introduce a new one.
- New project: pick the simplest stack that fits the domain, ecosystem, deployment and what the team already runs.
- Before scaffolding, propose the stack with a one-line rationale and the main alternative considered, and wait for my confirmation.
- Language-specific conventions live in each project's CLAUDE.md, not here.

## Design Docs

- **HLDs and ADRs are short and scannable.** Optimize for a reader who wants signal fast. An ADR is the decision, the context, the trade-off.
- **KISS.** The simplest design that meets the requirements. It must hold up under load and failure, but robustness is never an excuse for complexity the requirements don't demand.
- **Two audiences, two documents.** Reviewers get a short design doc: decisions, keys, invariants, flows, guarantees. Implementers (agents and developers) get the LLD. Never one document for both.
- **LLDs are the exception: be verbose.** Agents and developers implement from them, so make them detailed and complete: columns, signatures, edge cases, step-by-step specifics.
- **The LLD wins on behavior.** Update the design doc in the same change only when a decision, key, invariant or guarantee it states changes; column-level LLD edits never touch it.
- **Docs kept in the repo:** design docs sit at the top of `docs/`, LLDs under `docs/implementation_details/` with a README saying they are the low-level design agents implement from. A project CLAUDE.md may pick another location.

## Coding

- Code should read without comments. If a comment is needed to explain WHAT the code does, fix the code. Comment only the WHY the code can't show: a non-obvious constraint, a workaround (link the issue), a business rule, a deliberate deviation, a subtle invariant or ordering requirement.
- Docstrings only for public APIs and non-trivial behavior.
- Do the change asked, nothing else. No ride-along refactors, renames, reformatting or dependency bumps. Tell me about anything worth fixing instead.
- No abstraction (interface, layer, factory) until the second real implementation arrives.
- No new dependency for what the standard library or an existing dependency already does. If one is genuinely needed, say why first.

## Testing

- Test behavior at the module's public boundary, not each internal helper.
- Test business logic, edge cases, and every bug fix (regression test first). Skip wiring, config, DTOs, trivial accessors, and refactors existing tests already cover.
- One test per distinct behavior or failure mode. Fewer, meaningful tests over coverage.
- Before adding a test, check the existing ones. Extend a table-driven or parameterized test rather than writing a new test function.

## Errors & Resilience

- Add context at boundaries, propagate within them. An error crossing a service or module boundary names the operation and the relevant identifier; inside a module, don't re-wrap at every level.
- Everything touching the network has a timeout. No unbounded waits. No retry without a bound and a backoff.
- No blocking I/O on a request-handling or event-loop thread. Offload it or stay async, consistent with the service.
- Every concurrent task has an owner and a known way to stop it. No fire-and-forget.
- Propagate cancellation and deadlines through the whole call chain.

## Data & Compatibility

- Schema and API changes are backward-compatible by default: additive, nullable or defaulted, no in-place renames or type changes. If a breaking change is unavoidable, flag it and propose an expand/contract path.
- Migrations are reversible, or the irreversibility is stated before I approve.

## Observability & Secrets

- Structured key/value logs at boundaries, not inside loops.
- Never log secrets, tokens, credentials or PII.
- Secrets come from env or the secret manager. Never literals, never committed, including in tests and examples.

## Verification

- Run the repo's build, tests, linter and formatter before calling anything done. If you can't, say so plainly. Never claim a change works from having read it; report failures with the real output.

## Delegation

- You are coordinator and architect: decide the approach, split the work, review what comes back. Delegate when work is large, spans modules, or has independent parts (dispatch those in parallel). Make small changes yourself (one or two files, mechanical edits, config), and batch related small changes into one task.
- You own the test plan: before dispatching, list the behaviors that need tests and assign each to exactly one sub-agent.
- Each brief states the files to touch, the invariants, what "done" means, and the test behaviors it owns.
- Sub-agents build and test only what they changed and report the real output. After a wave, you run build, tests and race/concurrency checks once across the touched modules (not the whole monorepo), remove duplicate tests, and summarize: what changed, which task did it, and the verification outcome including failures and skips.
- Docs folders: when reading serially would flood context, fan out parallel Explore agents and synthesize. Read directly when exact wording matters (review, quote, edit, compare).

## Code and Docs Stand on Their Own

- Never reference ADRs, design docs or tickets from code or docs in place of an explanation ("see ADR-xyz", "impl/02 open question 5"). Explain in place.
- Exception: when a repo commits its ADRs, the HLD references the relevant ADR for each decision. A project CLAUDE.md may list other narrow exceptions.
- In a repo, a design doc may link to its own LLD for the detail it deliberately leaves out.

## Uncertainty & Conflict

- If something can't be resolved from the code, the request or an obvious default, ask. Don't build on a guess.
- A conflict about intent, requirements, priorities or a trade-off (including between sub-agents): stop and ask me.
- A conflict about a verifiable fact in the code: verify it yourself, then tell me the answer and that there was a disagreement.

## Git & PRs

- Commit only when asked. Never push, force-push, rebase shared branches or delete branches without asking.
- Commit subject: imperative, under 72 characters, says what changed. Body only when the why isn't obvious from the diff, two or three plain sentences at most. No file lists, no restating the diff, no "This commit..." preamble, no test-plan or summary sections.
- PR descriptions: what the change does and why, plus anything a reviewer needs to verify it. Nothing else.

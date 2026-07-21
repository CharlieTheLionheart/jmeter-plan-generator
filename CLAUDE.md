Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.

2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.


5. Use venv
When execute python3 command, always use the python3 under venv directory by sourcing the virtrual environment:
source venv ./venv/bin/activate && python3 xxx

6. After every change: test first, then smoke
- **UT first**: `python -m pytest tests/` → must pass before claiming "done".
- **Smoke second**: invoke the **`kwjdbc-jmx-smoke`** skill (don't roll your own command sequence). The skill owns the canonical `kwjdbc_svt.main` + `jmeter -n` end-to-end run against the real KaiwuDB cluster and reports setup / loader / sampler errors.
- "Tests pass" alone is not enough — smoke is the ground truth for this repo because the generators emit XML that JMeter executes against a running cluster.

7. After every fix: update @todolist.md
- Delete the solved entry (move to "已删" section if it was a real-but-wrongly-attributed bug).
- Keep only pending / unfixed issues under "遗留真问题".
- New commits get a new F-/L-id appended; completed F-ids move to "已完成" with the commit hash.
- Stale "已完成" entries get compressed to one line per fix (problem + fix + test + smoke) — not full paragraphs.
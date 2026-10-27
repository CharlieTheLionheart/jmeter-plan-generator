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

**每个 worktree 独立建 `.venv/`**（worktree 隔离依赖版本互不污染）。首次进 worktree 必须：

```bash
# 1. 创建 venv（只在 worktree 首次落地时做一次）
python -m venv .venv

# 2. 激活 + 安装核心 + dev 依赖（pytest 在 dev 组）
source .venv/bin/activate && pip install -e ".[dev]"
```

跑测试 / main 时一律：

```bash
source .venv/bin/activate && python -m pytest tests/
source .venv/bin/activate && python -m kwjdbc_svt.main ...
```

不要从父 repo 的 `venv/` 借 — 那是另一分支（`refactor/generic-test-plan`），import 会指向错代码。

`.venv/` 已加 .gitignore 屏蔽；不要 commit。

6. After every change: test first, then smoke
- **UT first**: `python -m pytest tests/` → must pass before claiming "done".
- **Smoke second**: invoke the **`kwjdbc-jmx-smoke`** skill (don't roll your own command sequence). The skill owns the canonical `kwjdbc_svt.main` + `jmeter -n` end-to-end run against the real KaiwuDB cluster and reports setup / loader / sampler errors.
- "Tests pass" alone is not enough — smoke is the ground truth for this repo because the generators emit XML that JMeter executes against a running cluster.

7. After every fix: update the active change's handoff(`openspec/changes/<change>/handoff.md`)
- Tick off completed sub-tasks in that change's `tasks.md`(`- [x]`);leave pending ones unchecked.
- Append each new commit to `handoff.md`(hash + 验证方式:pytest 结果 / smoke 证据)。
- Keep `handoff.md` 的「当前进度」「下一步」两节是最新的 —— 下一个会话应当**只读它就能续接**。
- handoff.md 的写法参考 `session-handoff-prompt` skill 的输出契约(结构稳定 + `[verified]` / `[inferred]` / `[unverified]` 事实标注)。
- 每个 change 一个 `handoff.md`;change 归档后该文件随 change 留在归档目录里。

## 语言规则

所有：
- 过程文档（spec / plan / tasks / proposal / design / handoff / README / TODO）
- 思考内容（chat 内的推理，不含 thinking block 原文）
- 返回内容（给用户的回复）

→ 中文输出。

例外（保留原文）：
- 技术术语、库 / 框架 / API 名
- Conventional Commits type（feat/fix/chore/docs/refactor/test/perf/build/ci/...）
- 代码块、文件路径、JSON key、错误字符串
- 代码标识符（类名 / 方法名 / 字段名 / 资源名 / GUID）

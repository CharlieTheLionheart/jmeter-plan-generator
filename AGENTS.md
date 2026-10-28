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

## 项目级规则：会话接续与实施档案

本项目的**会话接续**由 `handoff` skill 承担（接续文档写在工程根目录的 `handoff.md`，gitignored），
**实施决策档案**沉淀在 [`docs/implementation-log.md`](docs/implementation-log.md)（进 git）。所有实施会话必须遵守：

1. **会话开始前先读接续文档**——上一会话结束（或用户要求）时生成的 handoff 接续文档，回答"上次到哪儿了、下一步做什么"。该文档由 `handoff` skill 写在**工程根目录的 `handoff.md`**（已 gitignore；**不用 `/tmp`**——重启会丢）。
2. **需要历史决策时读实施档案**——[`docs/implementation-log.md`](docs/implementation-log.md) 回答"为什么这么做"：**已落地阶段一览**（做了哪些阶段）+ **§决策汇总**（每阶段做了什么 / 为什么 / 踩了什么坑与修法）+ **待办（跨会话）**。
3. **每个阶段完成后把决策写进实施档案**——在 `docs/implementation-log.md` 追加该阶段条目（做了什么 / 为什么 / 踩坑与修法 / 遗留），并同步"已落地阶段一览"与"待办（跨会话）"两节。
4. **代码与档案同 commit**——该阶段的代码改动与 `docs/implementation-log.md` 条目放在**同一个 commit** 里；**不追 commit hash**（填 hash 必须等 commit 产生，会逼出二次 commit）。
5. 阶段切分粒度遵循 `docs/implementation-log.md` 的"已落地阶段一览"；用户中途调整粒度需先更新该表。
6. OpenSpec change 的规格与任务清单留在 `openspec/changes/<change>/`（进 git），实施档案**不重复**其内容，只记录决策与教训。

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

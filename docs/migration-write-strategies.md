# write-strategies 合并重构迁移说明

本文档记录 `write-strategies` 一次性合并重构前后的差异面，作为 review §2（回滚计划）、§4（向后兼容）的合并闸门证据。

合并日期：2026-07-13
关联 change：`openspec/changes/write-strategies/`

---

## 合并前 vs 合并后

| 维度 | 合并前 | 合并后 |
| --- | --- | --- |
| `write_groups.py` 的 mode 分发 | `if wc.mode == "batch_prepared"` / `if wc.mode == "single_prepared"` 裸字符串判断 | `strategy = write_strategies.get_strategy(wc.mode); sampler_type = strategy.get_sampler_type()` |
| `scriptLanguage` 来源 | 硬编码 `"groovy"` 字面量 2 处（`write_groups.py:148,154`） | 从 `strategy.get_config("scriptLanguage", "groovy")` 读取 |
| `usePrepared` 来源 | 策略层返回但 jmx builder 不消费，xml 序列化时被丢弃 | `jdbc_sampler_element(use_prepared=strategy.get_config("usePrepared", False))`；仅 `True` 时写出 prop |
| JMX 默认字节 | 既定形态（无 `usePrepared` 元素） | 既定形态（默认 `False` 不写 prop） |
| `usePrepared=True` 路径 JMX | 无 `usePrepared` 元素 | 新增 `<stringProp name="usePrepared">true</stringProp>`（仅 `single_prepared` / 策略驱动路径） |

## JMX 输出差异面

合并前：write_groups 仅生成 `single_prepared` / `batch_prepared` 两种 ThreadGroup；JDBCSampler 元素不含 `usePrepared`；JSR223Sampler 的 scriptLanguage 硬编码 `"groovy"`。

合并后：
- `single_prepared` ThreadGroup 的 JDBCSampler **新增** `<stringProp name="usePrepared">true</stringProp>`（在 `resultSetHandler` 之后、`props` 之前）。
- `batch_prepared` ThreadGroup 的 JSR223Sampler / JSR223PreProcessor 的 scriptLanguage 仍为 `"groovy"`，但来源改为策略层 `BatchPreparedStatementStrategy.get_sampler_config()["scriptLanguage"]`。
- `single_insert` / `batch_insert` / `schemaless` 在 write_groups 这一层继续被 `continue` 跳过（关系表初始化走 SetupThreadGroup 路径）。

## 调用方变更清单

| 旧调用 | 新调用 |
| --- | --- |
| `if wc.mode == "batch_prepared"` (write_groups.py:143) | `if sampler_type == "JSR223Sampler"` (write_groups.py:143) |
| `if wc.mode == "single_prepared"` (write_groups.py:162) | `else` 分支，覆盖所有 `JDBCSampler` 策略（write_groups.py:162） |
| `script_language="groovy"` (write_groups.py:148,154) | `script_language=script_language` (从 `strategy.get_config("scriptLanguage", "groovy")` 读取) |
| `jdbc_sampler_element(...)` | `jdbc_sampler_element(..., use_prepared=use_prepared)` |

## 回退策略

无运行时回退开关。回归保证靠：

1. `tests/write_strategies/test_equivalence.py` 中 12 个 byte-identical 用例，断言策略层与 `direct_insert_write` 模块产出字节相同。
2. `tests/jmx_skeleton_generator/` 全套 78 个用例覆盖 `write_groups.generate_write_thread_groups` 的最终 JMX 形态。
3. `xml_helpers.jdbc_sampler_element(use_prepared=False)` 的默认形态与合并前完全一致；只有 `single_prepared` 调用点显式传 `True`，引入的 `usePrepared` 元素位置在 `resultSetHandler` 之后、`props` 之前。

如需排查兼容问题，回退路径：
- 还原 `write_groups.py` 中 `if sampler_type == "JSR223Sampler"` 为 `if wc.mode == "batch_prepared"`，还原 `script_language=` 硬编码字面量。
- 还原 `xml_helpers.py` 中 `use_prepared` 关键字参数与末尾追加逻辑。

## 未覆盖范围

- `jmx_skeleton_generator/generators/query_groups.py` 与 `shared_memory_initializer` 中硬编码的 `scriptLanguage="groovy"` 超出本次合并范围（见 plan "明确范围裁剪"）。
- `SchemalessWriteStrategy` 仍为 T2 延后 stub。
- `direct_insert_write` 公共 API 未删除，作为底层实现继续存在。

## 关联 tasks / review

- `openspec/changes/write-strategies/tasks.md` §10.3 §11.6 §12.2 已同步。
- `openspec/changes/write-strategies/review.md` §2 §3 §4 状态待翻转为 ✅ Resolved（提交 C4 末尾统一翻）。

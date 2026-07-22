## 1. 契约与过程文档

- [x] 1.1 更新原始规格，明确无关系表时不生成关系初始化子树
- [x] 1.2 更新原始设计文档，记录条件生成数据流和纯时序边界
- [x] 1.3 校验 proposal、design、delta spec、review 与实现范围一致

## 2. 条件关系初始化回归测试

- [x] 2.1 增加 DDL Setup 结构测试：空 `rel_init_specs` 不含 `RelInit_` 子树
- [x] 2.2 增加 skeleton/pipeline 端到端测试：纯时序模型无关系初始化元素
- [x] 2.3 增加正向测试：每张关系表仍生成一个初始化子树

## 3. 稀疏宽表前置修复

- [x] 3.1 验证并锁定 nullable 单元使用 `setObject(index, null)`，非 NULL 数值保持 typed setter
- [x] 3.2 修复并测试 4000 列 INSERT SQL 的 Groovy 字符串常量分块
- [x] 3.3 完成仅含 `t_cnc`、4000 个 nullable data columns、`null_rate=0.99` 的 model/config fixture

## 4. 验证与维护清单

- [x] 4.1 运行相关单元测试和全量 `python -m pytest tests/`
- [x] 4.2 运行 5 分钟 sparse KaiWuDB smoke，验证 0 error、写入行数和 99% NULL 种子
- [x] 4.3 运行原 shig canonical smoke，验证 0 error 和关系/时序表预期行数
- [ ] 4.4 更新 `todolist.md`：将 spec gap #3 移入已完成并记录测试、smoke 证据

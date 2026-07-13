## 0. 范围决策确认

- [x] 0.1 确认 `JMXSkeletonGenerator`（`src/jmx_skeleton_generator/generators/skeleton.py`）已封装完整 JMX 流水线；main.py 仅做 CLI + 配置加载 + 错误处理（design §"与现有 `JMXSkeletonGenerator` 的协作边界"）
- [x] 0.2 确认 review §1 Open Questions 收敛：文件名 `test_plan.jmx` / mode 校验在 config_parser / 种子目录 `seeds/{db}/{table}/`
- [x] 0.3 确认 JMX 合法性验证用 `xml.etree.ElementTree.parse()`（design §"收敛 review §3 JMX 合法性验证方式"）
- [x] 0.4 确认 `main(argv=None)` 签名 + 异常集中捕获 + 返回 exit code（programmatic 友好）

## 1. CLI 参数解析（argparse）

- [ ] 1.1 创建 `src/kwjdbc_svt/main.py`，含 `parse_args(argv=None)` 用标准库 argparse
- [ ] 1.2 接受两个位置参数：`test_model.yaml` 与 `test_cfg.yaml`
- [ ] 1.3 `-o/--output-dir` 可选 flag，默认当前工作目录
- [ ] 1.4 `-v/--verbose` flag：`-v` → INFO，`-vv` → DEBUG，默认 WARNING
- [ ] 1.5 `parse_args()` 返回 parsed args 对象用于单元测试（不直接调 sys.exit）

## 2. 日志配置

- [ ] 2.1 `setup_logging(verbose_level: int)` 配置 root logger 级别
- [ ] 2.2 统一 log format：`%(asctime)s [%(levelname)s] %(message)s`
- [ ] 2.3 main() 入口首句调 setup_logging；测试时 mock 避免污染

## 3. 配置加载与校验

- [ ] 3.1 `load_configs(args)` 调 `config_parser.parse_test_model_yaml` + `parse_test_cfg_yaml`
- [ ] 3.2 输入文件不存在 → 退出码 1（OSError，归到异常映射层）
- [ ] 3.3 捕获 `ValidationError`，日志输出全部错误，退出码 1
- [ ] 3.4 空文件 / null 根节点 → ValidationError 路径处理

## 4. Pipeline 编排（modulo `JMXSkeletonGenerator`）

- [ ] 4.1 `ColumnNamer(model_config)` 产出列名 lists
- [ ] 4.2 `seed_data_generator.generate_seeds(output_dir, model_config, column_names)` 写种子文件
- [ ] 4.3 `ddl_generator.generate(model_config, column_names)` 产出 DDL lists
- [ ] 4.4 检查 `test_config.write_config` 表 `mode` 字段；任一含 `single_prepared`/`batch_prepared` 则调 `prepared_insert_template.build_template_dict(...)`
- [ ] 4.5 全无 prepared mode → 跳过 `PreparedInsertTemplateGenerator`，传空 dict 给下一步
- [ ] 4.6 `JMXSkeletonGenerator(test_config, ddl_statements, prepared_templates, seed_csv_paths, output_dir).generate()` 产 .jmx 路径

## 5. 错误分类与退出码

- [ ] 5.1 实现 `map_exception_to_exit_code(exc) -> int` 中央映射
- [ ] 5.2 `ValidationError` → 1；`SeedGenError` → 2；`DdlGenerationError` → 3；`JmxGenerationError` → 4；其他 → 5
- [ ] 5.3 `main()` 把异常映射 exit code，不调 `sys.exit()`
- [ ] 5.4 DEBUG log 级别下，未知异常打印 traceback（`logging.exception`）

## 6. 主入口装配

- [ ] 6.1 `main(argv=None) -> int` 串联：setup_logging → parse_args → load_configs → pipeline → return 0
- [ ] 6.2 捕获 `KeyboardInterrupt` → 退出码 130
- [ ] 6.3 `if __name__ == "__main__": sys.exit(main())` 支持 `python -m kwjdbc_svt.main`

## 7. 单元测试

- [ ] 7.1 `parse_args()` 接受位置参数 + flags（无副作用，不污染 sys.argv）
- [ ] 7.2 `parse_args()` 缺位置参数 → 抛 `SystemExit`（argparse 默认行为）
- [ ] 7.3 `setup_logging(0)` → WARNING；`setup_logging(1)` → INFO；`setup_logging(2)` → DEBUG
- [ ] 7.4 `main()` 在 `ValidationError` 时返回 1
- [ ] 7.5 `main()` 在 `SeedGenError` 时返回 2（保留既有种子文件）
- [ ] 7.6 `main()` 在 `DdlGenerationError` 时返回 3
- [ ] 7.7 `main()` 在 `JmxGenerationError` 时返回 4
- [ ] 7.8 `main()` 在 `KeyError` 等未知异常时返回 5（DEBUG 打印 traceback）
- [ ] 7.9 prepared 跳过：write_config 全为 single_insert / batch_insert → PreparedInsertTemplateGenerator 不调

## 8. 集成测试（CLI E2E）

- [ ] 8.1 端到端：CLI 用样例 `test_model.yaml` + `test_cfg.yaml` → 产生 `test_plan.jmx` + `seeds/{db}/{table}/{i}_{col}.csv`
- [ ] 8.2 输出 .jmx 可被 `xml.etree.ElementTree.parse()` 解析
- [ ] 8.3 种子目录结构与既有 `seed_data_generator.__init__.py` 命名约定一致
- [ ] 8.4 覆盖场景：第二次执行产生 WARNING 日志 + 仍覆盖旧文件
- [ ] 8.5 `-o` 指向不存在父目录 → 自动创建
- [ ] 8.6 `-vv` 触发 DEBUG 日志输出

## 9. Review 修复验证

- [x] 9.1 review §1 三个 Open Questions 已在 design §"收敛 review §1 Open Questions" 落地
- [x] 9.2 review §3 JMX 合法性验证已选 `ElementTree.parse()` 路径
- [x] 9.3 review §4 兼容性：现 0 → 5 退出码映射覆盖业务异常所有已知类型
- [x] 9.4 review §5 任务粒度：本 tasks.md §1-§8 拆分按 exit-code + 模块边界，每个 task 单一可验收

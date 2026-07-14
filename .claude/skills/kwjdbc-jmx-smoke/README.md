# kwjdbc-jmx-smoke

kwjdbc-svt 端到端 JMX smoke 测试。

包了 `jmeter -n` 工作流，把 JMX 层 bug 在 CI 前拦截。

详见 [SKILL.md](SKILL.md)。

## 快速开始

```bash
# Claude Code 中，CLI / 生成器改动后：
/kwjdbc-jmx-smoke
```

skill 会：

1. 用 canonical fixtures 跑 `python -m kwjdbc_svt.main`
2. 对产出 .jmx 跑 `jmeter -n`
3. 对比已知真 bug fixtures 查回归
4. 输出结构化总结

## 来源

2026-07-13 `main-entry` 落地会话抓到的两个真 bug：

1. JDBC `initPool` parseInt `poolMax="${conn_pool_size}"` 字面
2. Shared-memory Groovy 用 OpenCSV (`CSVReader`)，JMeter classpath 没有

详见 SKILL.md `## 已知真 bug fixtures`。回归查 `git log -p c1b50f7`。

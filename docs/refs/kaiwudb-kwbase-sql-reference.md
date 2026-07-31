# KaiwuDB `kwbase sql` 命令参考（3.2.0）

> 来源：[kwbase CLI 工具总览](https://github.com/kwdb/kwdb/blob/3.2.0/docs/kaiwudb-tools/kwbase-cli-tool.md#kwbase-sql) + [kwbase CLI 部署](https://github.com/kwdb/kwdb/blob/3.2.0/docs/deployment/cluster-deployment/kwbase-cli-deployment.md)
>
> 用途：为 `rest-schemaless-write` change 的 setup / 验证 / 调试阶段提供 SQL Shell 命令速查，涵盖交互式连接、`-e` 一次性执行、连接参数（`--certs-dir` / `--insecure` / `--user` / `--url`）、输出格式与典型 smoke 场景。

## 1. 概述

`kwbase sql` 是 KWDB 提供的交互式 SQL Shell，支持：

- 交互式 REPL（默认进 shell）
- 一次性执行：`--execute` / `-e`
- 周期性执行：`--watch`
- TLS / 非安全模式连接
- 多种输出格式：`tsv` / `csv` / `table` / `records` / `sql` / `raw` / `html`

与客户端驱动（JDBC / libpq）共享同一 SQL 协议层，server 端行为一致。

## 2. 命令格式

```bash
./kwbase sql [flags]
```

最小可用命令：

```bash
# 非安全模式
./kwbase sql --insecure --host=127.0.0.1:26257

# TLS 安全模式
./kwbase sql --certs-dir=/etc/kaiwudb/certs --host=127.0.0.1:26257
```

## 3. 参数速查

### 3.1 连接参数

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| `--url` | `KWBASE_URL` | `postgresql://[user[:passwd]@]host[:port]/[db][?parameters...]` 完整 URL |
| `-u`, `--user` | `KWBASE_USER` | 数据库用户名 |
| `-d`, `--database` | `KWBASE_DATABASE` | 待连接数据库名 |
| `--insecure` | — | 非安全模式（明文） |
| `--certs-dir` | — | TLS 证书目录。默认 `${HOME}/.kaiwudb-certs/` |
| `--cert-principal-map` | — | `<cert-principal>:<db-principal>` 映射（逗号分隔） |
| `--host` | — | 必填。节点地址 `<host>:<port>` |

### 3.2 执行控制

| 参数 | 说明 |
|------|------|
| `-e`, `--execute` | 执行 SQL 后退出。允许多次指定；每次可含分号分隔的多语句。失败返回非零状态码 |
| `--watch` | 周期性重复执行 `--execute` 的语句。某次失败停止监控 |
| `--safe-updates` | 禁用无 `WHERE` 的 `DELETE` / `UPDATE`。默认 `true` |
| `--set` | SQL Shell 启动前设置客户端参数 |
| `--debug-sql-cli` | 简化 CLI，便于排查：回显 SQL、移除 prompt 中的 db/事务状态 |
| `--echo-sql` | 显示隐式发送的 SQL 语句 |

### 3.3 输出格式 `--format`

| 值 | 用途 |
|----|------|
| `tsv` | 默认（非交互式）。tab 分隔 |
| `csv` | 逗号分隔 |
| `table` | 默认（交互式）。对齐表格 |
| `records` | JSON 数组 |
| `sql` | `INSERT` 语句 |
| `raw` | 原始字节 |
| `html` | HTML 表格 |

判定规则：非交互式 → `tsv`，交互式 → `table`。

## 4. 典型用法

### 4.1 容器内一次性执行

```bash
# 安全模式 + 应用用户
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql \
  --certs-dir=/etc/kaiwudb/certs \
  --host=127.0.0.1:26257 \
  -e "SHOW USERS;"

# 安全模式 + 用户密码存在 kwbase sql 命令中
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql \
  --certs-dir=/etc/kaiwudb/certs \
  --host=127.0.0.1:26257 \
  -u root \
  -e "CREATE USER root WITH PASSWORD 'root123';"
```

### 4.2 一次性执行多语句

```bash
./kwbase sql --insecure --host=127.0.0.1:26257 \
  -e "CREATE DATABASE db_shig;
      CREATE DATABASE db_shig_rel;
      SHOW DATABASES;"
```

任一语句失败 → 退出码非零，已执行语句不回滚。

### 4.3 交互式 Shell

```bash
./kwbase sql --insecure --host=127.0.0.1:26257
```

```
# Welcome to the KWDB SQL interface.
# Type: \h for help with SQL commands.
#      \? for help with shell commands.
#      \q to quit.

root@127.0.0.1:26257/defaultdb> SHOW USERS;
  username | options  | member_of
-----------+----------+-----------
  root     | CREATEROLE | {admin}
  admin    | CREATEROLE | {}
(2 rows)
```

### 4.4 输出格式

```bash
# 默认 tsv（非交互）
./kwbase sql --insecure --host=127.0.0.1:26257 \
  -e "SELECT count(*) FROM db_shig_rel.workshop" --format=tsv

# table（适合人眼）
./kwbase sql --insecure --host=127.0.0.1:26257 \
  -e "SELECT * FROM db_shig_rel.workshop LIMIT 5" --format=table

# records（JSON 数组，自动化友好）
./kwbase sql --insecure --host=127.0.0.1:26257 \
  -e "SELECT now()" --format=records
```

### 4.5 URL 形式

```bash
./kwbase sql --url "postgresql://root:root123@127.0.0.1:26257/db_shig?sslmode=require&sslrootcert=/etc/kaiwudb/certs/ca.crt"
```

覆盖 `--host` / `--user` / `--database` / `--certs-dir` / `--insecure`。

## 5. 部署后建用户标准流程

来源：[kwbase CLI 部署 §6](https://github.com/kwdb/kwdb/blob/3.2.0/docs/deployment/cluster-deployment/kwbase-cli-deployment.md)

### 5.1 非安全模式（不带密码）

```bash
./kwbase sql --host=127.0.0.1:$local_port --insecure \
  -e "CREATE USER $username;
      GRANT admin TO $username WITH ADMIN OPTION;"
```

### 5.2 安全模式（带密码）

```bash
./kwbase sql --certs-dir=/usr/local/kaiwudb/certs --host=127.0.0.1:$local_port \
  -e "CREATE USER $username WITH PASSWORD \"$user_password\";
      GRANT admin TO $username WITH ADMIN OPTION;"
```

注意转义：shell 字符串需 `\"` 双重包裹。

## 6. 与本 change 的关键约束

| 约束 | 触发条件 | 文档出处 |
|------|---------|---------|
| `-e` 多语句失败不回滚 | 任意语句失败 | §4.2 |
| 安全模式 `--certs-dir` 必须存在 | container 未生成证书 | §3.1 |
| `--host` 必须含端口 | `<host>:<port>` 或 IP 直连 | §3.1 |
| `--insecure` 与 `--certs-dir` 互斥 | 启动模式二选一 | §3.1 |
| `--safe-updates` 默认 `true` | 限制无 WHERE 的 DELETE/UPDATE | §3.2 |
| 非交互式 `--format` 默认 `tsv` | 自动化场景 | §3.3 / §4.4 |

## 7. 失败模式与排错

| 错误 | 原因 | 修复 |
|------|------|------|
| `connection refused` | 节点未启动 / 端口错误 | `docker ps` + `--listen-addr` 对齐 |
| `cert verify failed` | `--certs-dir` 路径错 / CA 不匹配 | 检查 `ca.crt` 是否与节点同源 |
| `password authentication failed` | 用户密码与 `kwbase sql --user` 输入不一致 | 重新 `ALTER USER` 或 `--url` 中带入密码 |
| `permission denied` | 当前用户无 DDL 权限 | 用 `root` / `admin` 角色成员 |
| `unknown flag` | CLI 版本 < 3.2.0 | 升级 `kwbase` 或降级参数 |
| `database "xxx" does not exist` | `-d` 指定了未创建 db | `CREATE DATABASE` 或去掉 `-d` |

## 8. 与 SKILL.md §6.0 步骤的对应

`/home/liujin/workspace/quality-test-pipelines/kwjdbc-svt/.worktrees/20260723/rest-schemaless-write/.claude/skills/kwjdbc-jmx-smoke/SKILL.md` §6.0 容器 TLS 重建流程中，调 `kwbase sql` 建用户的步骤对应本文 §5.2：

```bash
# SKILL.md §6.0 的实际写法
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql \
  --certs-dir=/etc/kaiwudb/certs --host=127.0.0.1:26257 \
  -e "CREATE USER root WITH PASSWORD 'root123';"
```

环境差异：容器默认只有一个 `root` 用户（`admin` 角色），无需 `GRANT admin`。如需额外应用用户，复用 §5.2 模板。

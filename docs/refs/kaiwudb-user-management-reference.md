# KaiwuDB 用户管理参考（3.2.0）

> 来源：[用户管理（db-administration）](https://github.com/kwdb/kwdb/blob/3.2.0/docs/db-administration/user-mgmt.md) + [用户管理 SQL（sql-reference）](https://github.com/kwdb/kwdb/blob/3.2.0/docs/sql-reference/db-mgmt/user-mgmt-sql.md)
>
> 用途：为 `rest-schemaless-write` change 提供 KaiwuDB 3.2.0 用户管理 SQL 语法速查（`CREATE/ALTER/DROP USER` + `SHOW USERS` + 凭据机制），覆盖 setup 阶段容器建用户、smoke 准备、非空密码用户与 TLS 强绑定等场景。

## 1. 概述

KWDB 通过 `CREATE USER` / `ALTER USER` / `DROP USER` / `SHOW USERS` 四类 DDL 管理用户，权限模型基于 `CREATEROLE` 与 `admin` 角色。
默认 `root` 用户属于 `admin` 角色，可在初始化后立即创建/修改/删除其他用户。

```text
init 阶段 → root 用户（admin 角色 + 无密码，仅 --insecure 启动可用）
        ↓
ALTER USER root WITH PASSWORD 'xxx'    # 非安全模式：不支持，会 SQLSTATE 28P01
        ↓
CREATE USER appuser WITH PASSWORD 'xxx'  # 安全模式：必须带 PASSWORD
        ↓
GRANT admin TO appuser WITH ADMIN OPTION  # 提升为 admin
```

注意：`ALTER USER ... PASSWORD` 在 `--insecure` 启动的 KaiwuDB 容器中不被支持（SQLSTATE 28P01）。
**结论**：安全模式（`--certs-dir` + TLS）下才能创建非空密码用户；schemaless Login 强制非空密码用户 → 必须 TLS 启动。

## 2. 前提条件

- 已完成 `kwbase init`（集群已初始化）
- 当前连接用户为 `CREATEROLE` 角色或 `admin` 角色成员
- `ALTER USER` 额外要求：以安全模式登录 KWDB（即 `--certs-dir` + 客户端证书/密码）

## 3. CREATE USER

### 3.1 语法

```sql
CREATE USER [IF NOT EXISTS] <name> [WITH] [CREATEROLE | NOCREATEROLE | LOGIN | NOLOGIN | <password_clause> | <valid_until_clause>];
```

### 3.2 参数

| 参数 | 说明 |
|------|------|
| `IF NOT EXISTS` | 可选。存在同名用户时不报错，等于 no-op |
| `name` | 用户名。不区分大小写；以字母或下划线开头；仅字母/数字/下划线；长度 1-63 |
| `CREATEROLE` | 允许创建/修改/删除其他用户与角色 |
| `NOCREATEROLE` | 默认，禁止创建角色 |
| `LOGIN` | 默认，允许登录 |
| `NOLOGIN` | 禁止登录（角色用途） |
| `PASSWORD <string_or_placeholder>` | 单引号括起密码。支持 `NULL` 表示无密码 |
| `VALID UNTIL <string_or_placeholder>` | 密码过期时间。timestamp 格式，单引号。支持 `NULL` 表示永不过期 |

### 3.3 典型示例

```sql
-- 最小用户（无密码，可登录，不可创建角色）
CREATE USER user1;

-- 创建用户 + 允许创建角色
CREATE USER user2 WITH CREATEROLE;

-- 禁登录用户（角色用法）
CREATE USER user3 WITH NOLOGIN;

-- 完整：密码 + 过期时间
CREATE USER user4 WITH PASSWORD '11aa!!AA' VALID UNTIL '2023-01-01 00:00:00+00:00';
```

### 3.4 schemaless 场景推荐用法

```sql
-- 安全模式容器起步后立即创建非空密码用户
CREATE USER root WITH PASSWORD 'root123';

-- 应用用户（避免直接用 root）
CREATE USER appuser WITH PASSWORD 'app_secret_2026';
```

## 4. SHOW USERS / SHOW ROLES

### 4.1 语法

```sql
SHOW USERS;
-- 等价
SHOW ROLES;
```

无参数。所需权限：`system.users` / `system.role_members` 表的 `SELECT` 权限。

### 4.2 输出示例

```text
  username |                options                 | member_of
-----------+----------------------------------------+------------
  admin    | CREATEROLE                             | {}
  root     | CREATEROLE                             | {admin}
  user1    |                                        | {}
  user2    | CREATEROLE                             | {}
  user3    | NOLOGIN, VALID UNTIL=2023-12-31 00:00:00+00:00 | {}
  user4    | VALID UNTIL=2023-01-01 00:00:00+00:00  | {}
```

## 5. ALTER USER

### 5.1 语法

```sql
ALTER USER [IF EXISTS] <name> [WITH] [CREATEROLE | NOCREATEROLE | LOGIN | NOLOGIN | <password_clause> | <valid_until_clause>];
```

参数同 `CREATE USER`。`IF EXISTS` 行为同 `IF NOT EXISTS`。

### 5.2 典型示例

```sql
-- 修改密码 + 过期时间
ALTER USER user4 WITH PASSWORD '11aa!!AA' VALID UNTIL '2023-01-01 00:00:00+00:00';

-- 移除 CREATEROLE
ALTER USER user2 WITH NOCREATEROLE;
```

### 5.3 容器初始化典型流程

```bash
# 1. 容器以安全模式启动
docker run -d --name kaiwudb-smoke \
  --certs-dir=/etc/kaiwudb/certs \
  --listen-addr=0.0.0.0:26257 \
  --advertise-addr=127.0.0.1:26257 \
  --http-addr=0.0.0.0:8080 \
  --restful-port=8081 \
  kwdb/kwdb:latest start-single-node --background

# 2. ALTER USER 必须安全模式 —— insecure 启动时 SQLSTATE 28P01
docker exec kaiwudb-smoke /kaiwudb/bin/kwbase sql \
  --certs-dir=/etc/kaiwudb/certs --host=127.0.0.1:26257 \
  -e "CREATE USER root WITH PASSWORD 'root123';"
```

## 6. DROP USER

### 6.1 语法

```sql
DROP USER [IF EXISTS] <name>;
```

支持一次删除多个用户名（逗号分隔）。`IF EXISTS` 行为同 `IF NOT EXISTS`。

### 6.2 示例

```sql
DROP USER user1;
DROP USER IF EXISTS user2, user3;
```

## 7. 权限模型速查

| 操作 | 所需权限 |
|------|---------|
| `CREATE USER` | `CREATEROLE` 或 `admin` 角色成员 |
| `ALTER USER` | `CREATEROLE` 或 `admin` 角色成员 + 安全模式登录 |
| `DROP USER` | `CREATEROLE` 或 `admin` 角色成员 |
| `SHOW USERS` | `system.users` / `system.role_members` 表的 `SELECT` 权限 |

注意：`admin` 角色 ≠ `CREATEROLE`。`root` 默认同时拥有两者。普通 `CREATEROLE` 用户无法 `GRANT admin`，需要 `admin` 角色成员执行 `GRANT admin TO <user> WITH ADMIN OPTION;`。

## 8. 与本 change 的关键约束

| 约束 | 触发条件 | 文档出处 |
|------|---------|---------|
| `ALTER USER ... PASSWORD` 不支持 `--insecure` 集群 | SQLSTATE 28P01 | §1 概览 / §5.3 |
| `CREATE USER` 必须带 `PASSWORD` 以便 schemaless Login | 容器启动模式 + REST `/restapi/login` 鉴权 | §3.4 |
| `CREATE USER` 每条只能创建一个用户 | 语法限制 | §3.1 |
| 用户名最长 63 字符 | 语法限制 | §3.2 |
| `root` 默认属于 `admin` 角色 | 初始化后即可管理其他用户 | §2 / §7 |

## 9. 失败模式与排错

| 错误 | 原因 | 修复 |
|------|------|------|
| `SQLSTATE 28P01` | `--insecure` 集群 ALTER USER 密码 | 重建容器启用 TLS 或 `--certs-dir` |
| `user "xxx" already exists` | 重复 CREATE | 加 `IF NOT EXISTS` 或先 `DROP USER IF EXISTS` |
| `password authentication failed` | 用户密码与登录输入不一致 | 检查 `kwbase sql -u root -e "..."` 时 `--password` 参数 |
| `permission denied to create user` | 普通用户无 `CREATEROLE` | 用 `root` 执行或 `GRANT admin TO <user>` |

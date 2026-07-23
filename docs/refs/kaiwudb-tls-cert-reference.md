# KaiwuDB TLS 证书生成与使用参考

> 来源：[kwbase cert 子命令](https://doc.kaiwudb.com/template_version/pc/doc/kaiwudb-tools/kwbase-cli-tool.html#kwbase-cert) + [加密传输](https://doc.kaiwudb.com/template_version/pc/doc/db-security/transport-encryption.html)
>
> 用途：为 `rest-schemaless-write` change 的 `https_mode=tls` smoke 测试准备 `ca.crt`；为将来其他 REST/JDBC over TLS 场景提供证书生成与使用参考。

## 1. 证书体系总览

KaiwuDB 默认采用安全模式部署（TLS 或 TLCP）。启动时通过 `--certs-dir=<path>` 指定证书目录。

| 文件 | 内容 | 谁需要 |
|------|------|--------|
| `ca.crt` | CA 证书（公钥） | 客户端用于验证服务端 |
| `ca.key` | CA 私钥 | **仅服务端**用于签发其他证书 |
| `node.crt` / `node.key` | 节点证书 + 私钥 | 服务端 |
| `client.<user>.crt` / `.key` | 客户端证书 + 私钥 | 客户端（仅 mTLS 需要） |

REST API 路径（P0 scope）只需要 `ca.crt` —— 用 `Authorization: Basic <token>` 做身份认证，不走 mTLS。

## 2. 关键命令：`kwbase cert`

### 2.1 子命令

| 子命令 | 用途 |
|--------|------|
| `create-ca` | 生成 CA 证书 + 私钥 |
| `create-client-ca` | 生成客户端 CA 证书 + 私钥 |
| `create-node` | 生成节点证书 + 私钥（参数含节点 IP / hostname / localhost / 127.0.0.1） |
| `create-client` | 生成客户端证书 + 私钥（参数为 username） |
| `list` | 列出 `--certs-dir` 目录下的证书 |

### 2.2 公共参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--certs-dir` | `${HOME}/.kaiwudb-certs/` | 安全证书目录 |
| `--ca-key` | （无默认） | CA 私钥路径，**所有子命令必须**指定 |
| `--key-size` | `2048` | 密钥大小（比特） |
| `--lifetime` | `43920h0m0s`（~5 年） | 证书生命周期 |
| `--allow-ca-key-reuse` | `false` | create-ca / create-client-ca 是否复用已有 CA key |
| `--overwrite` | `false` | 是否覆写已存在证书 |
| `--tlcp` | `false` | 生成 TLCP 证书（默认 TLS） |
| `--cert-principal-map` | （无默认） | `<cert-principal>:<db-principal>` 映射，用于证书 Subject 字段受限制的系统 |

## 3. 生成最小证书集（REST 客户端用）

P0 场景下 REST 客户端只需 `ca.crt`。生成命令：

```bash
mkdir -p /tmp/kaiwudb-certs
mkdir -p /tmp/kaiwudb-ca

# 1. 创建 CA
./kwbase cert create-ca \
    --certs-dir=/tmp/kaiwudb-certs \
    --ca-key=/tmp/kaiwudb-ca/ca.key

# 2. 为节点生成证书（参数 = 节点 IP / hostname / localhost / 127.0.0.1）
./kwbase cert create-node <node_ip> localhost 127.0.0.1 \
    --certs-dir=/tmp/kaiwudb-certs \
    --ca-key=/tmp/kaiwudb-ca/ca.key

# 3. （mTLS 才需要；REST 跳过）创建客户端证书
# ./kwbase cert create-client root \
#     --certs-dir=/tmp/kaiwudb-certs \
#     --ca-key=/tmp/kaiwudb-ca/ca.key
```

服务端启动时指定 certs dir：

```bash
./kwbase start-single-node \
    --certs-dir=/tmp/kaiwudb-certs \
    --listen-addr=0.0.0.0:26257 \
    --advertise-addr=<your-host-ip>:26257 \
    --store=/tmp/kaiwudb-store
```

REST 客户端调用时引用 `ca.crt`：

```bash
curl -L --cacert /tmp/kaiwudb-certs/ca.crt \
     -H "Authorization: Basic <base64(user:pass)>" \
     -X GET https://<host>:8080/restapi/login
```

## 4. JMeter HTTPSampler 端的 `ca.crt` 引用

JMeter HTTP Request sampler 在 TLS 模式需两个属性（5.6+）：

```xml
<HTTPSamplerProxy ...>
    ...
    <stringProp name="HTTPSampler.customizedSslContext">/path/to/ca.crt</stringProp>
</HTTPSamplerProxy>

<!-- JMeter property 全局设置（部分版本需要） -->
<elementProp name="jmeterProperties">
    <stringProp name="ssl.keystore.file">/path/to/ca.crt</stringProp>
</elementProp>
```

在本仓库的 `rest-schemaless-write` change 中由 `http_request_sampler_element(ssl_context=...)` 参数透传，运行时 `${__P(rest_api.ca_cert_path)}` 展开为 `/path/to/ca.crt`。

## 5. 与现有 `kwjdbc-jmx-smoke` skill 的协同

`kwjdbc-jmx-smoke` 当前用 `kwdb/kwdb:latest` 或 `devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/kaiwudb/kwdb-x86_64-master:latest` 镜像 + `--insecure` 启动。**TLS smoke 是新增能力**：

- **不影响** insecure 路径：现有 fixture + smoke 流程不变
- **新增** TLS smoke 流程：build 阶段在 `kwjdbc-jmx-smoke` SKILL.md 加可选 `--tls` 模式，启动时 `kwbase cert create-ca` + `create-node` 生成证书，启动参数加 `--certs-dir=/tmp/kaiwudb-certs`
- **ca.crt 拷贝**：从容器 `/tmp/kaiwudb-certs/ca.crt` 拷到 JMeter 机器 `tests/kwjdbc_svt/fixtures/tls/ca.crt`，由 `test_cfg_schemaless.yaml::rest_api.ca_cert_path` 引用

## 6. 注意事项

- **证书生命周期 43920h ≈ 5 年**：smoke 证书不会过期；生产部署需关注 `lifetime` 与 `kwbase cert list` 输出
- **TLCP vs TLS**：默认 TLS；P0 smoke 用 TLS 即可；TLCP 需 `--tlcp` flag + 客户端 `--ssl-version TLCPv1.1`
- **Self-signed CA**：smoke 用 `create-ca` 生成的 CA 即 self-signed；生产部署建议用企业 CA 签发
- **REST API 不需要客户端证书**：服务端 TLS 校验靠 `ca.crt`；客户端身份认证走 `Authorization: Basic <token>`（参考 `kaiwudb-schemaless-write-reference.md` §6.1）
- **HTTP 路径切换**：KaiwuDB 同端口 `8080` 同时支持 HTTP 与 HTTPS（参考 `kaiwudb-schemaless-write-reference.md` §6.3）；`insecure` 与 `tls` 共用同一端口，`https_mode` 由 JMeter sampler `protocol` 字段切换

## 7. 与本仓库的对接清单

| 现状 | 影响 | build 阶段动作 |
|------|------|----------------|
| `kwjdbc-jmx-smoke` 现有 `--insecure` 启动路径 | 不变 | 无 |
| TLS smoke 需要 certs dir + ca.crt 跨容器/跨 JMeter 拷贝 | 新增 | `kwjdbc-jmx-smoke` SKILL.md 加 `--tls` 模式分支；Docker 容器内跑 `create-ca` + `create-node`；`docker cp` ca.crt 到 JMeter 主机 |
| `rest_api.ca_cert_path` 路径必须可达 | 静态配置 | `test_cfg_schemaless.yaml` 示例填 `tests/kwjdbc_svt/fixtures/tls/ca.crt`（git 跟踪测试用 CA，与 smoke 运行时生成的 CA 解耦） |
| 证书生成脚本可复用 | 新增 | `scripts/gen_kaiwudb_certs.sh` —— 接收 `--certs-dir` 与 `--ca-key` 参数；smoke 脚本调一次 |

## 8. 引用

- [kwbase cert 子命令文档](https://doc.kaiwudb.com/template_version/pc/doc/kaiwudb-tools/kwbase-cli-tool.html#kwbase-cert)
- [加密传输文档](https://doc.kaiwudb.com/template_version/pc/doc/db-security/transport-encryption.html)
- 本仓库引用：[kaiwudb-schemaless-write-reference.md](./kaiwudb-schemaless-write-reference.md) §6.1 Token 认证 / §6.3 HTTPS 双模式
- JMeter HTTPSampler 5.6+ 属性：[JMeter Component Reference](./jmeter-testplan-reference.md)（`HTTPSampler.customizedSslContext` 与 `ssl.keystore.file`）
# JMeter JMX 常用组件 XML 参考

---

## JMX 文件根结构

每个 `.jmx` 文件都是一个 XML 文档，根元素为 `jmeterTestPlan`，所有组件都包裹在 `<hashTree>` 层级节点中。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.x">
  <hashTree>
    <!-- TestPlan 必须是根节点下的第一个组件 -->
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan">
      <boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
    </TestPlan>
    <hashTree>
      <!-- 其他组件嵌套在此处 -->
    </hashTree>
  </hashTree>
</jmeterTestPlan>
```

**通用属性说明：**

| 属性 | 说明 |
|------|------|
| `guiclass` | GUI 面板类名（如 `TestPlanGui`） |
| `testclass` | 测试逻辑类名（如 `TestPlan`） |
| `testname` | 在测试树中显示的组件名称 |
| `enabled` | 是否启用（`true` / `false`） |

**通用子元素类型：**

| 元素 | 说明 |
|------|------|
| `stringProp` | 字符串属性 |
| `boolProp` | 布尔属性（`true` / `false`） |
| `intProp` | 整数属性 |
| `longProp` | 长整数属性 |
| `elementProp` | 嵌套复杂对象 |
| `collectionProp` | 集合/列表属性 |
| `objProp` | 对象属性（如 `SampleSaveConfiguration`） |

---

## 设计文档必需组件

以下组件直接来自 `kwdb-svt-test-plan-generator-design.md` 中选中的测试计划结构。

### TestPlan

测试计划根节点，每个 `.jmx` 文件必须有且仅有一个。

```xml
<TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan">
      <boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
    </TestPlan>
<hashTree>
  <!-- 所有其他组件放在此 hashTree 内 -->
</hashTree>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `TestPlan.functional_mode` | bool | 功能测试模式（如不配置使用默认值，默认值为false） |
| `TestPlan.serialize_threadgroups` | bool | 顺序执行线程组（如不配置使用默认值，默认值为false） |
| `TestPlan.tearDown_on_shutdown` | bool | 在主线程结束后执行Teardown线程组（如不配置使用默认值，默认值为false） |
| `TestPlan.user_defined_variables` | element | 用户自定义变量 |

---

### Arguments

用户自定义配置，用于声明用户自定义变量，暴露JMeter测试计划关键参数为流水线中执行测试计划时可设置的变量

```xml
<Arguments guiclass="ArgumentsPanel" testclass="Arguments" testname="[ConfigDebug] 预定义配置">
  <collectionProp name="Arguments.arguments">
    <elementProp name="db_url" elementType="Argument">
      <stringProp name="Argument.name">db_url</stringProp>
      <stringProp name="Argument.value">${__P(user.db.url,jdbc:kaiwudb://127.0.0.1:26257/defaultdb)}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
      <stringProp name="Argument.desc">数据库连接jdbc url, default: jdbc:kaiwudb://127.0.0.1:26257/defaultdb</stringProp>
    </elementProp>
    <elementProp name="db_user" elementType="Argument">
      <stringProp name="Argument.name">db_user</stringProp>
      <stringProp name="Argument.value">${__P(user.db.user,kaiwudb)}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
      <stringProp name="Argument.desc">数据库连接用户, default: kaiwudb</stringProp>
    </elementProp>
    <elementProp name="db_name" elementType="Argument">
      <stringProp name="Argument.name">db_name</stringProp>
      <stringProp name="Argument.value">${__P(user.db.name,db_shig)}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
      <stringProp name="Argument.desc">创建时时序库名称, default: db_shig</stringProp>
    </elementProp>
    <elementProp name="conn_pool_size" elementType="Argument">
      <stringProp name="Argument.name">conn_pool_size</stringProp>
      <stringProp name="Argument.value">${__P(user.sys.conn_pool_size,20)}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
      <stringProp name="Argument.desc">线程池大小, default: 20</stringProp>
    </elementProp>
    <elementProp name="data_ts_step" elementType="Argument">
      <stringProp name="Argument.name">data_ts_step</stringProp>
      <stringProp name="Argument.value">${__P(user.sys.data_ts_step,1)}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
      <stringProp name="Argument.desc">生成数据时间戳间隔ms, default: 1</stringProp>
    </elementProp>
    <elementProp name="device_count_per_thread" elementType="Argument">
      <stringProp name="Argument.name">device_count_per_thread</stringProp>
      <stringProp name="Argument.value">${__P(user.device.count_per_thread,50)}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
      <stringProp name="Argument.desc">每个线程模拟设备数量, default: 50</stringProp>
    </elementProp>
    <elementProp name="device_rand_start" elementType="Argument">
      <stringProp name="Argument.name">device_rand_start</stringProp>
      <stringProp name="Argument.value">${__P(user.device.rand_start,1)}</stringProp>
      <stringProp name="Argument.desc">起始设备编号,用于分布客户端创建,default: 1</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
    </elementProp>
    <!-- write_throughput UDV was removed 2026-09-11 (cfg-write-throughput-literal);
         per-table WriteConfig.throughput is baked into each write
         ConstantThroughputTimer as a literal string (samples/min/thread). -->
    <elementProp name="write_duration" elementType="Argument">
      <stringProp name="Argument.name">write_duration</stringProp>
      <stringProp name="Argument.value">${__P(user.write.duration,60)}</stringProp>
      <stringProp name="Argument.desc">写入持续时间,ISO8601时间格式-1表示不限制,default: 60</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
    </elementProp>
    <elementProp name="write_lines" elementType="Argument">
      <stringProp name="Argument.name">write_lines</stringProp>
      <stringProp name="Argument.value">${__P(user.write.lines,100)}</stringProp>
      <stringProp name="Argument.desc">单次单表插入数据行数: default:100</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
    </elementProp>
    <elementProp name="read_throughput" elementType="Argument">
      <stringProp name="Argument.name">read_throughput</stringProp>
      <stringProp name="Argument.value">${__P(user.read.throughput,60)}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
    </elementProp>
  </collectionProp>
</Arguments>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `Arguments.arguments` |  list | 用户自定义参数列表 |
| `Argument.name` | string | 用户自定义参数变量名 |
| `Argument.value` | string | 用户自定义参数变量值 |
| `Argument.metadata` | string | 用户自定义参数元数据，固定为= |
| `Argument.desc` | string | 用户自定义参数描述 |

---

### JDBCDataSource

JDBC 连接池配置，用于数据库连接管理。

```xml
<JDBCDataSource guiclass="TestBeanGUI" testclass="JDBCDataSource" testname="[JDBC] 创建数据库连接池" enabled="true">
  <stringProp name="dataSource">default_pool</stringProp>
  <stringProp name="poolMax">0</stringProp>
  <stringProp name="timeout">10000</stringProp>
  <stringProp name="trimInterval">60000</stringProp>
  <stringProp name="autocommit">${autocommit}</stringProp>
  <stringProp name="transactionIsolation">DEFAULT</stringProp>
  <boolProp name="preinit">true</boolProp>
  <stringProp name="initQuery">set enable_multimodel=true;</stringProp>
  <boolProp name="keepAlive">true</boolProp>
  <stringProp name="connectionAge">5000</stringProp>
  <stringProp name="checkQuery"></stringProp>
  <stringProp name="dbUrl">${db_url}</stringProp>
  <stringProp name="driver">com.kaiwudb.Driver</stringProp>
  <stringProp name="username">${db_user}</stringProp>
  <stringProp name="password"></stringProp>
  <stringProp name="connectionProperties"></stringProp>
</JDBCDataSource>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `dataSource` | string | 连接池变量名，JDBCSampler 通过此名称引用，对应GUI的`Variable Name for created pool` |
| `poolMax` | string | 连接池最大连接数（0 表示无限制），对应GUI的`Max Number of Connections(ms)` |
| `timeout` | string | 连接超时时间（毫秒），对应GUI的`Max Wait(ms)` |
| `trimInterval` | string | 连接池清理间隔，对应GUI的`Time Between Eviction Runs(ms)` |
| `autocommit` | bool | 是否自动提交，对应GUI的`Auto Commit` |
| `transactionIsolation` | string | 事务隔离级别（DEFAULT / TRANSACTION_READ_COMMITTED 等），对应GUI的`Transaction Isolation` |
| `preinit` | bool | 是否预初始化连接池，对应GUI的`Preinit Pool` |
| `initQuery` | string | 每连接的初始化设置查询语句，对应GUI的`Init SQL statements separated by new line` |
| `keepAlive` | bool | 是否保持连接活跃，对应GUI的`Test While Idle` |
| `connectionAge` | string | Idle连接最大存活时间，单位毫秒，对应GUI的`Soft Min Evictable Idle Time(ms)` |
| `checkQuery` | string | 检测有效连接的查询语句，可避免从pool拿到死连接，同时用于keepAlive检测，对应GUI的`Validation Query` |
| `dbUrl` | string | JDBC 连接 URL |
| `driver` | string | JDBC 驱动类全名 |
| `username` | string | 数据库用户名 |
| `password` | string | 数据库密码 |
| `connectionProperties` | string | 数据库连接属性，对应GUI的`Connection Properties` |

---

### SetupThreadGroup

setUp 线程组，在主测试开始前执行（如 DDL、数据准备）。

```xml
<SetupThreadGroup guiclass="SetupThreadGroupGui" testclass="SetupThreadGroup" testname="[Setup] 初始化">
  <intProp name="ThreadGroup.num_threads">1</intProp>
  <intProp name="ThreadGroup.ramp_time">1</intProp>
  <longProp name="ThreadGroup.duration">1</longProp>
  <longProp name="ThreadGroup.delay">1</longProp>
  <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
  <boolProp name="ThreadGroup.scheduler">true</boolProp>
  <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
  <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller">
    <stringProp name="LoopController.loops">1</stringProp>
    <boolProp name="LoopController.continue_forever">false</boolProp>
  </elementProp>
</SetupThreadGroup>
<hashTree>
  <!-- 嵌套 Sampler / Controller 等 -->
</hashTree>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `ThreadGroup.num_threads` | int / string | 线程数（虚拟用户数）。实际保存为 `intProp` 时表示常量，`stringProp` 时表示引用变量 |
| `ThreadGroup.ramp_time` | int | 启动所有线程所需时间（秒） |
| `ThreadGroup.duration` | long / string | 持续时间（秒）。实际保存为 `longProp` 时表示常量，`stringProp` 时表示引用变量 |
| `ThreadGroup.delay` | long | 启动延迟（秒） |
| `ThreadGroup.same_user_on_next_iteration` | bool | 每轮测试是否使用相同用户 |
| `ThreadGroup.scheduler` | bool | 是否启用调度器 |
| `ThreadGroup.on_sample_error` | string | 采样器错误时的动作：`continue` / `startnextloop` / `stopthread` / `stoptest` / `stoptestnow` |
| `LoopController.loops` | int / string | 循环次数（`-1` 表示无限） |
| `LoopController.continue_forever` | bool | 是否永远循环 |

---

### ThreadGroup

普通线程组，执行主要测试逻辑。

```xml
<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="[Write] 执行数据写入(random)" enabled="true">
  <stringProp name="ThreadGroup.num_threads">${conn_pool_size}</stringProp>
  <intProp name="ThreadGroup.ramp_time">1</intProp>
  <stringProp name="ThreadGroup.duration">${write_duration}</stringProp>
  <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
  <boolProp name="ThreadGroup.scheduler">true</boolProp>
  <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
  <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller">
    <stringProp name="LoopController.loops">1</stringProp>
    <boolProp name="LoopController.continue_forever">false</boolProp>
  </elementProp>
</ThreadGroup>
<hashTree>
  <!-- 嵌套 Timer / Sampler / PreProcessor 等 -->
</hashTree>
```

属性与 `SetupThreadGroup` 相同。

---

### JDBCSampler

执行 JDBC SQL 请求的采样器。

```xml
<JDBCSampler guiclass="TestBeanGUI" testclass="JDBCSampler" testname="写入数据: ${db_name}.t_electmeter: ${__threadNum}" enabled="true">
  <stringProp name="dataSource">default_pool</stringProp>
  <stringProp name="queryType">Update Statement</stringProp>
  <stringProp name="query">${builder}</stringProp>
  <stringProp name="queryArguments"></stringProp>
  <stringProp name="queryArgumentsTypes"></stringProp>
  <stringProp name="variableNames"></stringProp>
  <stringProp name="resultVariable"></stringProp>
  <stringProp name="queryTimeout">60</stringProp>
  <stringProp name="resultSetMaxRows"></stringProp>
  <stringProp name="resultSetHandler">Store as String</stringProp>
</JDBCSampler>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `dataSource` | string | 引用的 JDBCDataSource 变量名 |
| `queryType` | string | 查询类型：`Select Statement` / `Update Statement` / `Callable Statement` / `Prepared Select Statement` / `Prepared Update Statement` / `Commit` / `Rollback` |
| `query` | string | SQL 语句（不要带末尾分号） |
| `queryArguments` | string | 参数值（逗号分隔，用于 Prepared Statement） |
| `queryArgumentsTypes` | string | 参数类型（逗号分隔，如 `INTEGER,VARCHAR`） |
| `variableNames` | string | 结果变量名（逗号分隔） |
| `resultVariable` | string | 结果对象变量名 |
| `queryTimeout` | string | 查询超时时间，单位秒 |
| `resultSetMaxRows` | string | 结果集最大行数 |
| `resultSetHandler` | string | 结果集存储方式：`Store as String`（默认值）：把 ResultSet 转成字符串存到变量里；`Store as Object`：把 ResultSet 存成 Java 对象；`Count Records`：只统计行数，不存具体数据 |

---

### JSR223Sampler

使用脚本语言（如 Groovy）编写的自定义采样器。

```xml
<JSR223Sampler guiclass="TestBeanGUI" testclass="JSR223Sampler" testname="线程对象初始化" enabled="true">
  <stringProp name="scriptLanguage">groovy</stringProp>
  <stringProp name="parameters"></stringProp>
  <stringProp name="filename"></stringProp>
  <stringProp name="cacheKey">true</stringProp>
  <stringProp name="script">vars.putObject(&quot;last_ts&quot;, System.currentTimeMillis())
SampleResult.setIgnore()</stringProp>
</JSR223Sampler>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `scriptLanguage` | string | 脚本语言：`groovy` / `java` / `beanshell` / `javascript` / `jexl` 等 |
| `parameters` | string | 传入脚本的参数 |
| `filename` | string | 外部脚本文件路径（与 `script` 二选一） |
| `cacheKey` | string | 脚本编译缓存键（Groovy 等支持编译的语言有效），建议 `true` |
| `script` | string | 脚本内容 |

**脚本内置变量：**

| 变量 | 说明 |
|------|------|
| `vars` | JMeterVariables 对象，用于读写线程变量 |
| `props` | JMeterProperties 对象，用于读写全局属性 |
| `log` | Logger 对象，用于日志输出 |
| `ctx` | JMeterContext 对象，当前线程上下文 |
| `prev` | SampleResult 对象，前一个采样器的结果 |

---

### ConstantThroughputTimer

恒定吞吐量定时器，控制每分钟执行的请求数（RPS/分钟）。

```xml
<ConstantThroughputTimer guiclass="TestBeanGUI" testclass="ConstantThroughputTimer"
                          testname="Constant Throughput Timer" enabled="true">
  <stringProp name="throughput">60</stringProp>
  <intProp name="calcMode">0</intProp>
  <boolProp name="legacyMode">false</boolProp>
</ConstantThroughputTimer>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `throughput` | string | 目标吞吐量（每分钟采样数）。kwjdbc-svt 烤死为 cfg `WriteConfig.throughput` / `QueryConfig.throughput` 字面数值（无 UDV / `__BeanShell` 派生）；其它工具的派生公式不属本项目范围 |
| `calcMode` | int | 计算模式，固定为 `0`（This thread only），必须在 XML 中显式配置 |
| `legacyMode` | bool | 是否使用旧版计算模式（建议 `false`） |

> **注意：** `throughput` 的单位是 **samples per minute**。如果要控制每秒请求数，需要乘以 60。`calcMode=0` 表示每个线程独立计算吞吐量。

---

### JSR223PreProcessor

在采样器执行前运行的脚本预处理器。

```xml
<JSR223PreProcessor guiclass="TestBeanGUI" testclass="JSR223PreProcessor"
                     testname="JSR223 PreProcessor" enabled="true">
  <stringProp name="cacheKey">true</stringProp>
  <stringProp name="filename"></stringProp>
  <stringProp name="parameters"></stringProp>
  <stringProp name="script"></stringProp>
  <stringProp name="scriptLanguage">groovy</stringProp>
</JSR223PreProcessor>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `cacheKey` | string | 脚本编译缓存键（Groovy 等支持编译的语言有效），建议 `true` |
| `scriptLanguage` | string | 脚本语言：`groovy` / `java` / `beanshell` / `javascript` / `jexl` 等 |
| `script` | string | 脚本内容（与 `filename` 二选一） |
| `filename` | string | 外部脚本文件路径 |
| `parameters` | string | 传入脚本的参数 |

**脚本内置变量：** 与 `JSR223Sampler` 相同（`vars`、`props`、`log`、`ctx`、`prev`）。

> 用途：在采样器执行前修改变量、准备数据、计算动态参数等。

---

## 其他常用组件

---

### HTTPSamplerProxy

发送 HTTP / HTTPS 请求的采样器（JMeter GUI 中名为 "HTTP Request"）。属性完整参考见 [`jmeter-testplan-reference.md` §18.1 HTTP Request](jmeter-testplan-reference.md#http-request)。

**关键属性（helper 实际产出，P0 锁定）：**

| Property | 类型 | helper 行为 | 说明 |
|----------|------|------------|------|
| `HTTPSampler.domain` | string | **不产**（caller 写） | 必填（除非 HTTP Request Defaults 兜底） |
| `HTTPSampler.port` | int | **不产**（caller 写） | 监听端口 |
| `HTTPSampler.protocol` | enum | **不产**（caller 写） | `http` / `https` / `file` |
| `HTTPSampler.method` | enum | 总是产 | P0 仅 `GET`（Login）/ `POST`（其他） |
| `HTTPSampler.path` | string | 总是产 | URL 路径（`?db=` / `?tz=` 等 query string 拼在此） |
| `HTTPSampler.follow_redirects` | bool | 总是产 `true` | 是否跟随重定向（`follow_redirects=True` kwarg） |
| `HTTPSampler.auto_redirects` | bool | **总是产** `false` | JMeter 默认 false，写出仅为与 GUI 行为对齐 |
| `HTTPSampler.use_keepalive` | bool | 总是产 `true` | 设置 `Connection: keep-alive` |
| `HTTPSampler.DO_MULTIPART_POST` | bool | **总是产** `false` | P0 body 走 `text/plain`，不勾 multipart |
| `HTTPSampler.BROWSER_COMPATIBLE_MULTIPART` | bool | **总是产** `false` | multipart 时抑制 Content-Type 头，P0 不用 |
| `HTTPSampler.postBodyRaw` | bool | **条件产**：body 非空 `true`，body 空**省略** | body 是否走原始字节流 |
| `HTTPSampler.customizedSslContext` | string | **条件产**：`ssl_context` 非空 | TLS 客户端证书 keystore 路径 |

**helper 不产的 stringProp**（用 JMeter 默认值）：

- `HTTPSampler.connect_timeout` / `response_timeout`：JMeter 默认 0 = 无超时；与仓库现有 JDBC sampler 行为一致。
- `HTTPSampler.contentEncoding`：JMeter 默认空 = 不强制编码。

**HeaderManager 作为子 hashTree：**

HTTPSamplerProxy 通常与 `HeaderManager` 配对使用（每个 header 一个 `<elementProp name="" elementType="Header">` 含 `Header.name` + `Header.value`），位于 sampler 的**配对 hashTree 内**（即 `<HTTPSamplerProxy>` 之后紧跟的 `<hashTree>` 块内），这是 JMeter 5.x 解析时识别「这个 HeaderManager 配对给哪个 sampler」的依据。

**⚠ 关键约定（本仓库 P0 锁定）**：

1. Header **禁止**写成 `HTTPSampler.*` 顶层 stringProp（如 `HTTPSampler.contentType`）——JMeter 5.x 解析时会忽略。Header **必须**走 HeaderManager 子节点。
2. HeaderManager **必带** `<stringProp name="TestPlan.comments"></stringProp>` 节点（即使为空），匹配 JMeter 5.6.3 GUI 默认行为。
3. HTTPSamplerProxy **不**写 `<stringProp name="TestPlan.comments">`（与 HeaderManager 行为不同）。
4. helper **总是写** `HTTPSampler.auto_redirects` / `DO_MULTIPART_POST` / `BROWSER_COMPATIBLE_MULTIPART` 三个 boolProp 值 `false`（JMeter 默认等价；不优化）。
5. helper **不**写 `HTTPSampler.connect_timeout` / `response_timeout` / `contentEncoding` stringProp（JMeter 默认无超时 + 无编码；与仓库现有 JDBC sampler 行为一致）。
6. helper **条件写** `HTTPSampler.postBodyRaw`（body 非空时 `true`，body 空时省略该 boolProp）。
7. helper **条件写** `HTTPSampler.customizedSslContext` + `ssl.keystore.file`（`ssl_context` 参数非空时）。

**P0 形态 A — GET + 无 body + HeaderManager**（用于 `GET /restapi/login`）：

`HTTPsampler.Arguments` 整节点**省略**（既无 body 也无 Parameters 表）；helper 不产 `postBodyRaw`（body 空）。`HTTPSampler.domain` / `port` / `protocol` 由调用方在 sampler properties 子树里插入（helper 不产）。

```xml
<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="${testname}" enabled="true">
  <stringProp name="HTTPSampler.domain">${domain}</stringProp>
  <stringProp name="HTTPSampler.port">${port}</stringProp>
  <stringProp name="HTTPSampler.protocol">${protocol}</stringProp>
  <stringProp name="HTTPSampler.path">${path}</stringProp>
  <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
  <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
  <stringProp name="HTTPSampler.method">GET</stringProp>
  <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
  <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
  <boolProp name="HTTPSampler.BROWSER_COMPATIBLE_MULTIPART">false</boolProp>
</HTTPSamplerProxy>
<hashTree>
  <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="${testname}" enabled="true">
    <collectionProp name="HeaderManager.headers">
      <elementProp name="" elementType="Header">
        <stringProp name="Header.name">${name}</stringProp>
        <stringProp name="Header.value">${value}</stringProp>
      </elementProp>
      <elementProp name="" elementType="Header">
        <stringProp name="Header.name">${name2}</stringProp>
        <stringProp name="Header.value">${value2}</stringProp>
      </elementProp>
      <!-- 多个 header 重复上 elementProp 块 -->
    </collectionProp>
    <stringProp name="TestPlan.comments"></stringProp>
  </HeaderManager>
  <hashTree/>
</hashTree>
```

**P0 形态 B — POST + raw body + HeaderManager**（用于 `POST /restapi/ddl` / `POST /restapi/influxdb?db=...` / `POST /restapi/query`）：

`postBodyRaw=true`；`HTTPsampler.Arguments` 节点无 `guiclass`/`testclass`/`testname`（raw body 模式，GUI 不显示 Key/Value 表）；单条 `HTTPArgument` `name=""` + `always_encode=false` + `Argument.value=${body}` + `Argument.metadata==`。

```xml
<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="${testname}" enabled="true">
  <stringProp name="HTTPSampler.domain">${domain}</stringProp>
  <stringProp name="HTTPSampler.port">${port}</stringProp>
  <stringProp name="HTTPSampler.protocol">${protocol}</stringProp>
  <stringProp name="HTTPSampler.path">${path}</stringProp>
  <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
  <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
  <stringProp name="HTTPSampler.method">POST</stringProp>
  <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
  <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
  <boolProp name="HTTPSampler.BROWSER_COMPATIBLE_MULTIPART">false</boolProp>
  <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
  <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
    <collectionProp name="Arguments.arguments">
      <elementProp name="" elementType="HTTPArgument">
        <boolProp name="HTTPArgument.always_encode">false</boolProp>
        <stringProp name="Argument.value">${body}</stringProp>
        <stringProp name="Argument.metadata">=</stringProp>
      </elementProp>
    </collectionProp>
  </elementProp>
</HTTPSamplerProxy>
<hashTree>
  <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="${testname}" enabled="true">
    <collectionProp name="HeaderManager.headers">
      <elementProp name="" elementType="Header">
        <stringProp name="Header.name">${name}</stringProp>
        <stringProp name="Header.value">${value}</stringProp>
      </elementProp>
    </collectionProp>
    <stringProp name="TestPlan.comments"></stringProp>
  </HeaderManager>
  <hashTree/>
</hashTree>
```

**P0 形态 C — TLS 变体**（`https_mode=tls` 时使用）：

在 P0 形态 B 基础上加：

1. `<stringProp name="HTTPSampler.protocol">https</stringProp>`
2. HTTPSamplerProxy 内追加：
   ```xml
   <stringProp name="HTTPSampler.customizedSslContext">${ca_cert_path}</stringProp>
   ```
3. **JMeter property**（在 JMX `<elementProp name="TestPlan.user_defined_variables">` 之外、通过 `-J` 或 JMX 根 properties 注入）：
   ```
   ssl.keystore.file = ${ca_cert_path}
   ```
   P0 通过 `kwjdbc_svt/main.py` 启动时 `-Jssl.keystore.file=${ca_cert_path}` 传 JMeter CLI；不在 JMX 节点里写。

**辅助函数**（`src/utils/xml_helpers.py`）：

- `http_request_sampler_element(method: str, path: str, headers: Dict[str, str], body: str, ssl_context: Optional[str] = None, *, name: str, testname: str, follow_redirects: bool = True) -> Tuple[Element, Element]`：返回 `(sampler, hashTree)` 元组；hashTree 已含一个 HeaderManager 子节点（若 `headers` 非空）。`headers` 是 `{header_name: header_value}` 字典（Python 3.7+ 字典迭代顺序稳定，XML 序列化确定性）。`body=""` 时不写 `HTTPsampler.Arguments` 整节点（适用 P0 形态 A）且不产 `HTTPSampler.postBodyRaw` boolProp。`ssl_context` 非空时在 sampler 内追加 `HTTPSampler.customizedSslContext` + `ssl.keystore.file` 两个 stringProp。**调用方**必须在 sampler properties 子树里手动插入 `HTTPSampler.domain` / `port` / `protocol`（helper 不产）。调用方需把返回的 `(sampler, hashTree)` 顺序追加到父 hashTree。
- `header_manager_element(headers: Dict[str, str], testname: str) -> Element`：生成 HeaderManager 元素；**自带**空 `<stringProp name="TestPlan.comments">` 节点；调用方需自己配对一个 `<hashTree/>` 兄弟节点。

**P0 用途表**（KaiwuDB 无模式写入 — 见 `kaiwudb-schemaless-write-reference.md`）：

| 用途 | method | path | 必填 headers | body | 形态 |
|------|--------|------|-------------|------|------|
| Login | `GET` | `/restapi/login?tz=${tz}`（tz 可选） | `Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic base64(${user}:${pass})` | 空 | P0-A |
| DDL pre-create | `POST` | `/restapi/ddl` | `Content-Type: text/plain`、`Accept: application/json`、`Authorization: Basic ${rest_token}` | 单条 `CREATE TABLE` SQL | P0-B |
| InfluxDB write | `POST` | `/restapi/influxdb?db=${db}` | 同上 | 单行 / 多行 InfluxDB Line protocol | P0-B |
| Query round-trip | `POST` | `/restapi/query` | 同上 | `SELECT` / `SHOW` SQL | P0-B |

**CDATA 约定：** JMeter 默认**不**使用 CDATA 包裹 body——`Argument.value` 直接以 stringProp 文本写入，ElementTree / lxml 在序列化时会按需对 `<` / `>` / `&` 做实体转义，JMeter 解析时反转义回原字符。本仓库 JMX 沿用此形式（与 JDBC Sampler 一致），无 `<![CDATA[…]]>`。

---

**P1+ 参考 — POST + Parameters tab**（`/restapi/opentsdbjson` 等表单端点；P0 不用）

与 P0-B 区别：`HTTPsampler.Arguments` 顶层 elementProp 带 `guiclass="HTTPArgumentsPanel"` + `testclass="Arguments"` + `testname="User Defined Variables"`；每个 `HTTPArgument` 带 `name` + `use_equals=true` + `content_type=text/plain`，`always_encode=true`。

**P1+ 参考 — POST + multipart**（文件上传端点；P0 不用）

在 P0-B 基础上加 `<boolProp name="HTTPSampler.DO_MULTIPART_POST">true</boolProp>` + `<boolProp name="HTTPSampler.BROWSER_COMPATIBLE_MULTIPART">true</boolProp>`；每个 `HTTPArgument` 自带 `<stringProp name="HTTPArgument.content_type">${mime}</stringProp>`。

---

### ResponseAssertion

响应断言，用于验证采样器结果。

```xml
<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion"
                    testname="Assertion" enabled="true">
  <collectionProp name="Asserion.test_strings">
    <stringProp name="-868354929">&lt;h1&gt;Example Domain&lt;/h1&gt;</stringProp>
  </collectionProp>
  <stringProp name="Assertion.custom_message"></stringProp>
  <stringProp name="Assertion.test_field">Assertion.response_data</stringProp>
  <boolProp name="Assertion.assume_success">false</boolProp>
  <intProp name="Assertion.test_type">16</intProp>
</ResponseAssertion>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `Asserion.test_strings` | collection | 断言字符串列表 |
| `Assertion.custom_message` | string | 断言失败时的自定义提示信息 |
| `Assertion.test_field` | string | 断言字段：`Assertion.response_data` / `Assertion.response_code` / `Assertion.response_message` / `Assertion.response_headers` |
| `Assertion.assume_success` | bool | 断言失败时是否标记为成功 |
| `Assertion.test_type` | int | 断言类型（位掩码）：1=Contains, 2=Matches, 4=Equals, 8=Substring, 16=Not |

---

### LoopController

循环控制器，控制子采样器的执行次数。

```xml
<LoopController guiclass="LoopControlPanel" testclass="LoopController" testname="循环写入" enabled="true">
  <boolProp name="LoopController.continue_forever">true</boolProp>
  <intProp name="LoopController.loops">-1</intProp>
</LoopController>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `LoopController.continue_forever` | bool | 是否永远循环。为 `true` 时忽略 `loops` |
| `LoopController.loops` | int / string | 循环次数，`-1` 表示无限循环；也可使用变量引用如 `${loops}` |

---

### ResultCollector (View Results Tree)

结果收集器 / 查看结果树监听器。

```xml
<ResultCollector guiclass="ViewResultsFullVisualizer" testclass="ResultCollector"
                  testname="View Results Tree" enabled="true">
  <boolProp name="ResultCollector.error_logging">false</boolProp>
  <objProp>
    <name>saveConfig</name>
    <value class="SampleSaveConfiguration">
      <time>true</time>
      <latency>true</latency>
      <timestamp>true</timestamp>
      <success>true</success>
      <label>true</label>
      <code>true</code>
      <message>true</message>
      <threadName>true</threadName>
      <dataType>true</dataType>
      <encoding>false</encoding>
      <assertions>true</assertions>
      <subresults>true</subresults>
      <responseData>false</responseData>
      <samplerData>false</samplerData>
      <xml>false</xml>
      <fieldNames>true</fieldNames>
      <responseHeaders>false</responseHeaders>
      <requestHeaders>false</requestHeaders>
      <responseDataOnError>false</responseDataOnError>
      <saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>
      <assertionsResultsToSave>0</assertionsResultsToSave>
      <bytes>true</bytes>
      <sentBytes>true</sentBytes>
      <url>true</url>
      <threadCounts>true</threadCounts>
      <idleTime>true</idleTime>
      <connectTime>true</connectTime>
      <sampleCount>true</sampleCount>
      <hostname>true</hostname>
    </value>
  </objProp>
  <stringProp name="filename"></stringProp>
</ResultCollector>
<hashTree/>
```

**关键属性：**

| Property | 类型 | 说明 |
|----------|------|------|
| `ResultCollector.error_logging` | bool | 是否只记录错误 |
| `saveConfig` | objProp | `SampleSaveConfiguration` 对象，控制保存/显示哪些字段 |
| `filename` | string | 结果保存文件路径，空表示不保存到文件 |

---

## 嵌套关系速查

根据设计文档中的测试计划结构，组件嵌套关系如下：

```
jmeterTestPlan
└── hashTree
    └── TestPlan
        └── hashTree
            ├── JDBCDataSource
            │   └── hashTree/
            ├── SetupThreadGroup (DDL 执行)
            │   └── hashTree
            │       ├── JDBCSampler (建库建表)
            │       │   └── hashTree/
            │       └── JDBCSampler (初始化元数据)
            │           └── hashTree/
            ├── ThreadGroup (生成实时数据)
            │   └── hashTree
            │       ├── ConstantThroughputTimer
            │       │   └── hashTree/
            │       └── JSR223Sampler
            │           └── hashTree
            │               └── JSR223PreProcessor
            │                   └── hashTree/
            ├── ThreadGroup (写入数据)
            │   └── hashTree
            │       ├── ConstantThroughputTimer
            │       │   └── hashTree/
            │       └── JDBCSampler (batch_prepared)
            │           └── hashTree
            │               └── JSR223PreProcessor
            │                   └── hashTree/
            └── ThreadGroup (查询)
                └── hashTree
                    ├── ConstantThroughputTimer
                    │   └── hashTree/
                    └── JDBCSampler (prepared_statement)
                        └── hashTree/
```

**嵌套规则：**
- 每个组件后面必须紧跟一个 `<hashTree>` 节点
- `hashTree` 为空时写为 `<hashTree/>`
- `hashTree` 包含子组件时，子组件按 **组件 + hashTree** 对依次排列
- 同级组件是顺序关系，父子组件是嵌套关系
# JMeter JSR223 内置变量 一页速查版（Groovy）

## 零、强制规范（必守）

- 默认使用 **Groovy**，禁止 BeanShell

- 脚本内禁止 `${}` 取值，只用代码取值

- 禁止 print 输出，统一使用 `log` 日志

- 字符串用 `put/get`，对象/集合强制 `putObject/getObject`

## 一、变量作用域速览

|变量|作用域|核心用途|
|---|---|---|
|**vars**|单线程私有（隔离）|常规参数存取（90%场景首选）|
|**props**|全局所有线程|跨线程/跨线程组传值、全局配置|
|**prev**|单线程|读取上一个取样器响应结果|
|**ctx**|全局上下文|线程/测试引擎控制|
|**log**|全局|分级日志输出|
|**args**|当前组件|读取组件入参|

## 二、vars 线程变量（高频）

```Plain Text
// 字符串读写
vars.put("key", "value");
String s = vars.get("key");

// 对象读写（List/Map/JSON）
vars.putObject("obj", [1,2,3]);
def obj = vars.getObject("obj");

// 工具方法
vars.remove("key");
boolean exist = vars.get("key") != null;
```

## 三、props 全局变量（跨线程专用）

```Plain Text
// 全局字符串
props.put("global_key", "123");
String g = props.get("global_key");

// 全局对象
props.put("global_list", ["a","b"]);
def gList = props.get("global_list");

// 删除
props.remove("global_key");
```

## 四、prev 上一个请求结果（断言/提取）

```Plain Text
// 核心信息
String body = prev.getResponseDataAsString(); // 响应体
String code = prev.getResponseCode();         // 响应码
long time = prev.getTime();                   // 耗时(ms)

// 手动控制用例成败
prev.setSuccessful(true);                     // 成功
prev.setSuccessful(false);                    // 失败
prev.setResponseMessage("自定义失败原因");
```

## 五、ctx 上下文控制

```Plain Text
ctx.getThreadNum();          // 当前线程号
ctx.getThreadGroup().getName();// 线程组名
ctx.getThread().stop();      // 停止当前线程
ctx.getEngine().stopTest();  // 停止整个测试（慎用）
```

## 六、log 日志分级输出

```Plain Text
log.info("常规日志");
log.warn("警告日志");
log.error("错误日志", e); // 打印异常堆栈
log.debug("调试日志");
```

## 七、args 组件入参读取

组件 Parameters 填：`val1,val2`

```Plain Text
log.info(args[0]);
log.info(args[1]);
```

## 八、经典场景一句话方案

- **同线程传参**：只用 vars

- **跨线程/线程组传参**：只用 props

- **存 List/Map/JSON**：一律 putObject

- **接口结果校验**：prev 取值 \+ 手动 setSuccessful

## 九、极简避坑清单

- ✅ 脚本取值：`vars.get("key")` \| ❌ 禁止：`${key}`

- ✅ 对象存储：`putObject` \| ❌ 禁止：普通 put

- ✅ 跨线程：props \| ❌ 禁止：vars

- ✅ 输出日志：log \| ❌ 禁止：print

> （注：文档部分内容可能由 AI 生成）

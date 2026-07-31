"""JMeter XML element helpers for building JMX files.

Key JMX nesting rule (from real JMeter 5.x files):
  Every component element is ALWAYS followed by exactly one <hashTree>:
    - Empty hashTree → <hashTree/>  (self-closing)
    - Non-empty hashTree → <hashTree> children </hashTree>

  The hashTree is a SIBLING of the component, not a child.

Correct structure:
  <TestPlan ...>
    ...props...
  </TestPlan>
  <hashTree>
    <Arguments ...>
      ...props...
    </Arguments>
    <hashTree/>
    <JDBCDataSource ...>
      ...props...
    </JDBCDataSource>
    <hashTree/>
    <SetupThreadGroup ...>
      ...props...
    </SetupThreadGroup>
    <hashTree>
      <JDBCSampler ...>
        ...props...
      </JDBCSampler>
      <hashTree/>
    </hashTree>
  </hashTree>

All helpers conform to the JMeter 5.5+ DTD.
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union
from xml.etree import ElementTree as ET

# JMeter namespace used as the default in JMX files
JMETER_NS = "http://jmeter.apache.org/"

ET.register_namespace("", JMETER_NS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _q(tag: str) -> str:
    """Qualify a local tag name with the JMeter namespace."""
    return f"{{{JMETER_NS}}}{tag}"


# ---------------------------------------------------------------------------
# Low-level element factory
# ---------------------------------------------------------------------------

def make_element(
    tag: str,
    *,
    name: Optional[str] = None,
    testname: Optional[str] = None,
    attributes: Optional[dict[str, str]] = None,
    text: Optional[str] = None,
    children: Optional[List[ET.Element]] = None,
) -> ET.Element:
    """Create a JMeter XML element.

    Parameters
    ----------
    tag:
        Local tag name (e.g. ``"ThreadGroup"``).
    name:
        Value for the element's ``name`` attribute.
    testname:
        Value for the element's ``testname`` attribute (display name in JMeter tree).
    attributes:
        Additional XML attributes as ``{attr: value}`` dict.
    text:
        Inner text for leaf elements.
    children:
        Child elements appended in order.

    Returns
    -------
    A xml.etree.ElementTree.Element instance.
    """
    attribs: dict[str, str] = {}
    if name is not None:
        attribs["name"] = name
    if testname is not None:
        attribs["testname"] = testname
    if attributes:
        attribs.update(attributes)

    elem = ET.Element(_q(tag), attribs)
    if text is not None:
        elem.text = text
    if children:
        for child in children:
            elem.append(child)
    return elem


# ---------------------------------------------------------------------------
# Property element helpers
# ---------------------------------------------------------------------------

def string_prop(name: str, text: str) -> ET.Element:
    """Create a ``<stringProp name="...">`` element."""
    return make_element("stringProp", name=name, text=text)


def bool_prop(name: str, text: str) -> ET.Element:
    """Create a ``<boolProp name="...">`` element (``true`` / ``false``)."""
    return make_element("boolProp", name=name, text=text)


def int_prop(name: str, text: Union[int, str]) -> ET.Element:
    """Create an ``<intProp name="...">`` element."""
    return make_element("intProp", name=name, text=str(text))


def long_prop(name: str, text: Union[int, str]) -> ET.Element:
    """Create a ``<longProp name="...">`` element."""
    return make_element("longProp", name=name, text=str(text))


def element_prop(
    name: str,
    element_type: str,
    *,
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    attributes: Optional[dict[str, str]] = None,
) -> ET.Element:
    """Create an ``<elementProp>`` element.

    Parameters
    ----------
    name:
        The ``name`` attribute (used as the variable/key name in JMeter).
    element_type:
        The fully-qualified JMeter GUI class, e.g. ``Arguments``.
    props:
        Child property elements (``stringProp``, ``boolProp``, etc.).
    testname:
        Display name in the JMeter tree.
    attributes:
        Additional XML attributes.
    """
    attribs = dict(attributes or {})
    attribs["elementType"] = element_type
    return make_element(
        "elementProp",
        name=name,
        testname=testname,
        attributes=attribs,
        children=props or [],
    )


def collection_prop(
    name: str,
    *,
    children: Optional[List[ET.Element]] = None,
    attributes: Optional[dict[str, str]] = None,
) -> ET.Element:
    """Create a ``<collectionProp>`` element.

    Parameters
    ----------
    name:
        The ``name`` attribute.
    children:
        Child elements (typically ``elementProp``).
    attributes:
        Additional XML attributes.
    """
    attribs = dict(attributes or {})
    return make_element(
        "collectionProp",
        name=name,
        attributes=attribs,
        children=children or [],
    )


# ---------------------------------------------------------------------------
# hashTree helpers
# ---------------------------------------------------------------------------

def empty_hash_tree() -> ET.Element:
    """Create an empty ``<hashTree/>`` self-closing element."""
    return make_element("hashTree")


def hash_tree(*children: ET.Element) -> ET.Element:
    """Create a ``<hashTree>`` element containing child elements.

    When no children are passed, returns an empty self-closing hashTree.
    """
    elem = make_element("hashTree")
    for child in children:
        elem.append(child)
    return elem


# ---------------------------------------------------------------------------
# Component + hashTree pair helpers
#
# Every JMeter component must be followed by a hashTree sibling.
# These helpers return (component, hashTree) pairs so the caller can
# append them in the correct alternating sequence.
# ---------------------------------------------------------------------------

def argument_element(
    name: str = "UserDefinedVariables",
    *,
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    guiclass: str = "ArgumentsPanel",
    testclass: str = "Arguments",
    attributes: Optional[dict[str, str]] = None,
) -> Tuple[ET.Element, ET.Element]:
    """Create an ``<Arguments>`` element and its paired ``<hashTree>``.

    Returns
    -------
    (Arguments element, hashTree element).
    """
    attribs = {"guiclass": guiclass, "testclass": testclass}
    if attributes:
        attribs.update(attributes)
    args = make_element(
        "Arguments",
        name=name,
        testname=testname or name,
        attributes=attribs,
        children=props or [],
    )
    return args, empty_hash_tree()


def test_plan_element(
    name: str = "TestPlan",
    *,
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    guiclass: str = "TestPlanGui",
    testclass: str = "TestPlan",
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<TestPlan>`` element and its paired ``<hashTree>``.

    Returns
    -------
    (TestPlan element, hashTree element).
    """
    tp = make_element(
        "TestPlan",
        name=name,
        testname=testname or name,
        attributes={"guiclass": guiclass, "testclass": testclass},
        children=props or [],
    )
    return tp, empty_hash_tree()


def setup_thread_group_element(
    name: str,
    *,
    num_threads: Union[int, str] = 1,
    ramp_time: Union[int, str] = 1,
    duration: Optional[str] = None,
    delay: Union[int, str] = 0,
    loops: Union[int, str] = 1,
    scheduler: bool = True,
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    guiclass: str = "SetupThreadGroupGui",
    testclass: str = "SetupThreadGroup",
    children: Optional[List[ET.Element]] = None,
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<SetupThreadGroup>`` element and its paired ``<hashTree>``.

    ``children`` are appended into the paired ``<hashTree>`` so JMeter
    recognises them as belonging to this thread group instead of as
    siblings at the enclosing hashTree level (the legacy
    ``empty_hash_tree`` return path had this bug).
    """
    all_props: List[ET.Element] = [
        string_prop("SetupThreadGroup.on_sample_error", "continue"),
        string_prop("ThreadGroup.num_threads", str(num_threads)),
        string_prop("ThreadGroup.ramp_time", str(ramp_time)),
        string_prop("ThreadGroup.duration", str(duration) if duration else ""),
        string_prop("ThreadGroup.delay", str(delay)),
        bool_prop("ThreadGroup.same_user_on_next_iteration", "true"),
        bool_prop("ThreadGroup.scheduler", "true" if scheduler else "false"),
        element_prop(
            name="ThreadGroup.main_controller",
            element_type="LoopController",
            testname="Loop Controller",
            props=[
                string_prop("LoopController.loops", str(loops)),
                bool_prop("LoopController.continue_forever", "false"),
            ],
        ),
    ]
    if props:
        all_props.extend(props)

    stg = make_element(
        "SetupThreadGroup",
        name=name,
        testname=testname or name,
        attributes={"guiclass": guiclass, "testclass": testclass},
        children=all_props,
    )
    stg_hash = hash_tree(*(children or []))
    return stg, stg_hash


def thread_group_element(
    name: str,
    *,
    num_threads: Union[int, str] = 1,
    ramp_time: Union[int, str] = 1,
    duration: Optional[str] = None,
    delay: Union[int, str] = 0,
    loops: Union[int, str] = "-1",
    scheduler: bool = True,
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    guiclass: str = "ThreadGroupGui",
    testclass: str = "ThreadGroup",
    children: Optional[List[ET.Element]] = None,
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<ThreadGroup>`` element and its paired ``<hashTree>``.

    ``children`` are appended into the paired ``<hashTree>`` so JMeter
    recognises them as belonging to this thread group.
    """
    all_props: List[ET.Element] = [
        string_prop("ThreadGroup.num_threads", str(num_threads)),
        string_prop("ThreadGroup.ramp_time", str(ramp_time)),
        string_prop("ThreadGroup.duration", str(duration) if duration else ""),
        string_prop("ThreadGroup.delay", str(delay)),
        bool_prop("ThreadGroup.same_user_on_next_iteration", "true"),
        bool_prop("ThreadGroup.scheduler", "true" if scheduler else "false"),
        string_prop("ThreadGroup.on_sample_error", "continue"),
        element_prop(
            name="ThreadGroup.main_controller",
            element_type="LoopController",
            testname="Loop Controller",
            props=[
                string_prop("LoopController.loops", str(loops)),
                bool_prop("LoopController.continue_forever", "false"),
            ],
        ),
    ]
    if props:
        all_props.extend(props)

    tg = make_element(
        "ThreadGroup",
        name=name,
        testname=testname or name,
        attributes={"guiclass": guiclass, "testclass": testclass},
        children=all_props,
    )
    tg_hash = hash_tree(*(children or []))
    return tg, tg_hash


def jdbc_sampler_element(
    name: str,
    query: str = "",
    *,
    data_source: str = "default_pool",
    query_type: str = "Update Statement",
    query_arguments: str = "",
    query_arguments_types: str = "",
    variable_names: str = "",
    result_variable: str = "",
    query_timeout: str = "60",
    result_set_max_rows: str = "",
    result_set_handler: str = "Store as String",
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    enabled: bool = True,
    guiclass: str = "TestBeanGUI",
    testclass: str = "JDBCSampler",
    use_prepared: bool = False,
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<JDBCSampler>`` element and its paired ``<hashTree/>``.

    Parameters
    ----------
    name:
        Internal name.
    query:
        SQL query string (or a JMeter variable).
    data_source:
        JDBC Data Source pool variable name.
    query_type:
        Query type: ``Update Statement``, ``Select Statement``,
        ``Prepared Update Statement``, ``Prepared Select Statement``, etc.
    query_arguments:
        Comma-separated argument values for prepared statements.
    query_arguments_types:
        Comma-separated JDBC type names for query_arguments.
    variable_names:
        Comma-separated variable names to capture results.
    result_variable:
        Variable name to store the entire result set.
    query_timeout:
        Query timeout in seconds.
    result_set_max_rows:
        Maximum rows to retain from the result set.
    result_set_handler:
        How to store results: ``Store as String`` (default) | ``Store as Object`` | ``Count Records``.
    props:
        Additional property elements appended after defaults.
    testname:
        Display name in the JMeter tree (defaults to ``name``).
    enabled:
        Whether the element is enabled.
    use_prepared:
        Whether the JMeter GUI treats the statement as prepared. Default
        ``False`` preserves the historical XML shape; set ``True`` from
        ``WriteStrategy.get_config("usePrepared")`` when the strategy
        drives sampler generation.
    """
    all_props: List[ET.Element] = [
        string_prop("dataSource", data_source),
        string_prop("queryType", query_type),
        string_prop("query", query),
        string_prop("queryArguments", query_arguments),
        string_prop("queryArgumentsTypes", query_arguments_types),
        string_prop("variableNames", variable_names),
        string_prop("resultVariable", result_variable),
        string_prop("queryTimeout", query_timeout),
        string_prop("resultSetMaxRows", result_set_max_rows),
        string_prop("resultSetHandler", result_set_handler),
    ]
    # 仅在策略/上游明示 use_prepared=True 时写出 usePrepared；
    # 默认 False 保持与既有 jmx_skeleton_generator 输出字节相同。
    if use_prepared:
        all_props.append(string_prop("usePrepared", "true"))
    if props:
        all_props.extend(props)

    sampler = make_element(
        "JDBCSampler",
        name=name,
        testname=testname or name,
        attributes={
            "guiclass": guiclass,
            "testclass": testclass,
            "enabled": "true" if enabled else "false",
        },
        children=all_props,
    )
    return sampler, empty_hash_tree()


def jdbc_data_source_element(
    name: str,
    db_url: str,
    driver: str,
    *,
    pool_max: str = "${conn_pool_size}",
    timeout: str = "10000",
    trim_interval: str = "60000",
    autocommit: str = "true",
    transaction_isolation: str = "DEFAULT",
    preinit: bool = True,
    init_query: str = "",
    keep_alive: bool = True,
    connection_age: str = "5000",
    check_query: str = "",
    username: str = "",
    password: str = "",
    connection_properties: str = "",
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    enabled: bool = True,
    guiclass: str = "TestBeanGUI",
    testclass: str = "JDBCDataSource",
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<JDBCDataSource>`` element and its paired ``<hashTree/>``.

    Parameters
    ----------
    name:
        Pool variable name (used in JDBCSampler's ``dataSource`` attribute).
    db_url:
        JDBC connection URL.
    driver:
        Fully-qualified JDBC driver class name.
    pool_max:
        Max connections (``0`` = unlimited).
    timeout:
        Connection timeout in milliseconds.
    autocommit:
        Auto-commit mode (``true`` / ``false``).
    transaction_isolation:
        Transaction isolation level.
    preinit:
        Pre-initialise the connection pool.
    init_query:
        SQL executed on each new connection.
    keep_alive:
        Test connections on idle.
    connection_age:
        Max idle connection lifetime in milliseconds.
    check_query:
        Validation query (runs on checkout).
    username:
        Database username.
    password:
        Database password.
    connection_properties:
        Additional JDBC connection properties.
    props:
        Additional property elements appended after defaults.
    testname:
        Display name in the JMeter tree.
    """
    all_props: List[ET.Element] = [
        string_prop("dataSource", name),
        string_prop("poolMax", pool_max),
        string_prop("timeout", timeout),
        string_prop("trimInterval", trim_interval),
        string_prop("autocommit", autocommit),
        string_prop("transactionIsolation", transaction_isolation),
        bool_prop("preinit", "true" if preinit else "false"),
        string_prop("initQuery", init_query),
        bool_prop("keepAlive", "true" if keep_alive else "false"),
        string_prop("connectionAge", connection_age),
        string_prop("checkQuery", check_query),
        string_prop("dbUrl", db_url),
        string_prop("driver", driver),
        string_prop("username", username),
        string_prop("password", password),
        string_prop("connectionProperties", connection_properties),
    ]
    if props:
        all_props.extend(props)

    ds = make_element(
        "JDBCDataSource",
        name=name,
        testname=testname or name,
        attributes={
            "guiclass": guiclass,
            "testclass": testclass,
            "enabled": "true" if enabled else "false",
        },
        children=all_props,
    )
    return ds, empty_hash_tree()


def jsr223_preprocessor_element(
    name: str,
    script: str = "",
    *,
    script_language: str = "groovy",
    parameters: str = "",
    filename: str = "",
    cache_key: str = "true",
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    enabled: bool = True,
    guiclass: str = "TestBeanGUI",
    testclass: str = "JSR223PreProcessor",
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<JSR223PreProcessor>`` element and its paired ``<hashTree/>``.

    Parameters
    ----------
    name:
        Internal name.
    script:
        Inline script content.
    script_language:
        Script language (e.g. ``groovy``).
    parameters:
        Parameters passed to the script.
    filename:
        External script file path (mutually exclusive with ``script``).
    cache_key:
        Use compiled script cache (``true`` recommended for Groovy).
    props:
        Additional property elements appended after defaults.
    testname:
        Display name in the JMeter tree.
    """
    all_props: List[ET.Element] = [
        string_prop("cacheKey", cache_key),
        string_prop("filename", filename),
        string_prop("parameters", parameters),
        string_prop("script", script),
        string_prop("scriptLanguage", script_language),
    ]
    if props:
        all_props.extend(props)

    proc = make_element(
        "JSR223PreProcessor",
        name=name,
        testname=testname or name,
        attributes={
            "guiclass": guiclass,
            "testclass": testclass,
            "enabled": "true" if enabled else "false",
        },
        children=all_props,
    )
    return proc, empty_hash_tree()


def jsr223_sampler_element(
    name: str,
    script: str = "",
    *,
    script_language: str = "groovy",
    parameters: str = "",
    filename: str = "",
    cache_key: str = "true",
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    enabled: bool = True,
    guiclass: str = "TestBeanGUI",
    testclass: str = "JSR223Sampler",
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<JSR223Sampler>`` element and its paired ``<hashTree/>``.

    Parameters
    ----------
    name:
        Internal name.
    script:
        Inline script content.
    script_language:
        Script language (e.g. ``groovy``).
    parameters:
        Parameters passed to the script.
    filename:
        External script file path (mutually exclusive with ``script``).
    cache_key:
        Use compiled script cache (``true`` recommended for Groovy).
    props:
        Additional property elements appended after defaults.
    testname:
        Display name in the JMeter tree.
    """
    all_props: List[ET.Element] = [
        string_prop("cacheKey", cache_key),
        string_prop("filename", filename),
        string_prop("parameters", parameters),
        string_prop("script", script),
        string_prop("scriptLanguage", script_language),
    ]
    if props:
        all_props.extend(props)

    sampler = make_element(
        "JSR223Sampler",
        name=name,
        testname=testname or name,
        attributes={
            "guiclass": guiclass,
            "testclass": testclass,
            "enabled": "true" if enabled else "false",
        },
        children=all_props,
    )
    return sampler, empty_hash_tree()


def constant_throughput_timer_element(
    name: str = "Constant Throughput Timer",
    throughput: str = "${throughput}",
    calc_mode: int = 0,
    *,
    props: Optional[List[ET.Element]] = None,
    testname: Optional[str] = None,
    enabled: bool = True,
    guiclass: str = "TestBeanGUI",
    testclass: str = "ConstantThroughputTimer",
) -> Tuple[ET.Element, ET.Element]:
    """Create a ``<ConstantThroughputTimer>`` element and its paired ``<hashTree/>``.

    Parameters
    ----------
    name:
        Internal name.
    throughput:
        Target throughput (samples per minute), or a variable reference.
    calc_mode:
        Calculation mode (``0`` = This thread only).
    """
    all_props: List[ET.Element] = [
        string_prop("throughput", throughput),
        int_prop("calcMode", calc_mode),
        bool_prop("legacyMode", "false"),
    ]
    if props:
        all_props.extend(props)

    timer = make_element(
        "ConstantThroughputTimer",
        name=name,
        testname=testname or name,
        attributes={
            "guiclass": guiclass,
            "testclass": testclass,
            "enabled": "true" if enabled else "false",
        },
        children=all_props,
    )
    return timer, empty_hash_tree()


# ---------------------------------------------------------------------------
# HTTP sampler helper (REST 线程组基础构造器)
# ---------------------------------------------------------------------------

def http_request_sampler_element(
    method: str,
    path: str,
    headers: dict[str, str],
    body: str,
    ssl_context: Optional[str] = None,
    *,
    name: str,
    testname: str,
    follow_redirects: bool = True,
) -> Tuple[ET.Element, ET.Element]:
    """构造 ``<HTTPSamplerProxy>`` 元素及其配对 ``<hashTree>``。

    面向 REST（schemaless / InfluxDB line protocol）写入与查询线程组的
    基础 sampler 构造器，Task 2/3/4 均复用本函数。

    Parameters
    ----------
    method:
        HTTP 方法，``"GET" | "POST" | "PUT"``。
    path:
        请求路径，通常是 JMeter 变量引用，如 ``"${rest_api.write_url_path}"``。
    headers:
        已解析好的请求头 ``{名: 值}`` 字典（含 ``Authorization``，不要传模板占位）。
        每个键值对生成 HeaderManager 里的一个 ``Header`` 节点。
    body:
        原始请求体字符串；空串表示无请求体，此时不写 ``postBodyRaw``、
        也不产出 ``Argument.value`` 节点。非空 body 原样写入，
        JMeter 变量（如 ``${request_body}``）在运行时展开。
    ssl_context:
        CA 证书路径字符串；非空时写入两个属性
        （``HTTPSampler.customizedSslContext`` 与 ``ssl.keystore.file``），
        ``None`` 时不产出任何 ssl 节点。
    name:
        sampler 名称。
    testname:
        JMeter 树中的显示名（当前调用方与 ``name`` 相同）。
    follow_redirects:
        是否跟随重定向；``auto_redirects`` 恒为 ``false``。

    Returns
    -------
    ``(HTTPSamplerProxy 元素, hashTree 元素)``。HeaderManager 位于配对
    hashTree 内，并紧跟其自身的空 hashTree 兄弟节点。

    Notes
    -----
    ``protocol`` / ``port`` / ``domain`` 由调用方在 sampler properties
    子树里写入（沿用现有 ``HTTPSampler.protocol`` 约定），本函数不产出
    这三项，避免与调用方重复。
    """
    # Arguments 子树：body 非空时塞入一个 HTTPArgument 承载原始请求体。
    arg_props: List[ET.Element] = []
    if body:
        arg_props.append(
            element_prop(
                name="",
                element_type="HTTPArgument",
                props=[
                    bool_prop("HTTPArgument.always_encode", "false"),
                    string_prop("Argument.value", body),
                    string_prop("Argument.metadata", "="),
                ],
            )
        )
    arguments = element_prop(
        name="HTTPsampler.Arguments",
        element_type="Arguments",
        testname="User Defined Variables",
        props=[collection_prop("Arguments.arguments", children=arg_props)],
    )

    sampler_props: List[ET.Element] = [
        arguments,
        string_prop("HTTPSampler.path", path),
        string_prop("HTTPSampler.method", method),
        bool_prop("HTTPSampler.follow_redirects", "true" if follow_redirects else "false"),
        bool_prop("HTTPSampler.auto_redirects", "false"),
        bool_prop("HTTPSampler.use_keepalive", "true"),
        bool_prop("HTTPSampler.DO_MULTIPART_POST", "false"),
        bool_prop("HTTPSampler.BROWSER_COMPATIBLE_MULTIPART", "false"),
    ]
    if body:
        sampler_props.append(bool_prop("HTTPSampler.postBodyRaw", "true"))
    if ssl_context:
        sampler_props.append(string_prop("HTTPSampler.customizedSslContext", ssl_context))
        sampler_props.append(string_prop("ssl.keystore.file", ssl_context))

    sampler = make_element(
        "HTTPSamplerProxy",
        name=name,
        testname=testname,
        attributes={
            "guiclass": "HttpTestSampleGui",
            "testclass": "HTTPSamplerProxy",
            "enabled": "true",
        },
        children=sampler_props,
    )

    # HeaderManager：每个 header 生成一个 Header 节点。
    header_props = [
        element_prop(
            name=hname,
            element_type="Header",
            props=[
                string_prop("Header.name", hname),
                string_prop("Header.value", hvalue),
            ],
        )
        for hname, hvalue in headers.items()
    ]
    header_manager = make_element(
        "HeaderManager",
        name="HTTP Header Manager",
        testname="HTTP Header Manager",
        attributes={
            "guiclass": "HeaderPanel",
            "testclass": "HeaderManager",
            "enabled": "true",
        },
        children=[collection_prop("HeaderManager.headers", children=header_props)],
    )

    sampler_hash = hash_tree(header_manager, empty_hash_tree())
    return sampler, sampler_hash


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def to_string(element: ET.Element, *, encoding: str = "UTF-8") -> str:
    """Serialize an element tree to a UTF-8 encoded XML string.

    Uses ElementTree's built-in serialization which correctly handles
    the JMeter default namespace and produces self-closing <hashTree/>
    tags for empty elements.
    """
    tree = ET.ElementTree(element)
    ET.indent(tree, space="  ")
    return ET.tostring(tree.getroot(), encoding=encoding, xml_declaration=True).decode(encoding)


def write_jmx(element: ET.Element, path: str, *, encoding: str = "UTF-8") -> None:
    """Write an element tree to a JMX file.

    Parameters
    ----------
    element:
        Root element.
    path:
        Output file path (including ``.jmx`` extension).
    encoding:
        Output character encoding.
    """
    tree = ET.ElementTree(element)
    ET.indent(tree, space="  ")
    with open(path, "wb") as f:
        f.write(f'<?xml version="1.0" encoding="{encoding}"?>\n'.encode(encoding))
        tree.write(f, encoding=encoding)

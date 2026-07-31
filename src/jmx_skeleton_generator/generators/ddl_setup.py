"""DDL SetupThreadGroup generator."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.rest_errors import RestConfigError
from utils.xml_helpers import (
    bool_prop,
    element_prop,
    empty_hash_tree,
    hash_tree,
    http_request_sampler_element,
    jdbc_sampler_element,
    jsr223_preprocessor_element,
    make_element,
    setup_thread_group_element,
    string_prop,
)


# Default batch size for relational-table initialisation. Spec §3.6
# mandates ``total_rows % batch_lines == 0``; using a value that
# cleanly divides the largest common seed_num keeps the no-tail-batch
# invariant trivial (1 residue row causes a hard error).
_DEFAULT_REL_BATCH_LINES = 100


def generate_ddl_setup_thread_group(
    ddl_statements: List[str],
    *,
    name: str = "DDL Setup",
    num_threads: int = 1,
    rel_init_specs: Optional[Sequence[Dict[str, Any]]] = None,
) -> List:
    """Build a SetupThreadGroup that runs all DDL statements plus
    relational-table initialisation samplers.

    Parameters
    ----------
    ddl_statements:
        DDL SQL strings (CREATE DATABASE, CREATE TABLE, etc.).
        Each gets its own JDBCSampler.
    name:
        Display name for the setup thread group.
    num_threads:
        Number of threads (default 1).
    rel_init_specs:
        Optional iterable of spec dicts (one per relational table).
        Each dict must contain:

        - ``table_name`` (str, qualified ``db.table``)
        - ``columns`` (list[str], in DDL order)
        - ``total_rows`` (int, must be a positive multiple of
          ``batch_lines``)
        - ``batch_lines`` (int, default ``_DEFAULT_REL_BATCH_LINES``)
        - ``rel_col_seed_files`` (list[str], one entry per ``columns``)
        - ``column_types`` (list[str], aligned with ``columns``; defaults
          to all VARCHAR when omitted)

        When present, each spec produces a ``LoopController`` containing a
        :class:`JSR223PreProcessor` for batch parameter assembly and a
        ``Prepared Update Statement`` JDBCSampler, all placed in the
        SetupThreadGroup's paired hashTree right after the DDL samplers.

    Returns
    -------
    A 2-element list ``[SetupThreadGroup, hashTree]`` whose hashTree
    contains all DDL JDBCSampler + their paired hashTrees. Returns an
    empty list when neither DDL nor relational initialisation are
    requested.
    """
    children: List = []
    for i, ddl in enumerate(ddl_statements):
        sampler, samp_hash = jdbc_sampler_element(
            name=f"DDL-{i + 1}",
            query=ddl,
            data_source="jdbcConfig",
            query_type="Update Statement",
            testname=f"DDL-{i + 1}",
        )
        children.extend([sampler, samp_hash])
    for spec in rel_init_specs or []:
        children.extend(_build_rel_init_subtree(spec))

    if not children:
        return []

    stg, stg_hash = setup_thread_group_element(
        name=name,
        testname=name,
        num_threads=num_threads,
        ramp_time=1,
        duration="${test_duration}",
        delay=0,
        loops=1,
        scheduler=True,
        children=children,
    )
    return [stg, stg_hash]


def _build_rel_init_subtree(spec: Dict[str, Any]) -> List:
    """Build the LoopController subtree (with sampler + preprocessor) for one
    relational-table initialisation spec.

    The returned flat list contains:

    - The ``<LoopController>`` element
    - Its paired ``<hashTree>`` containing the JDBCSampler + PreProcessor
      (each with their own paired hashTree)
    - The closing ``<hashTree>`` that pairs with the JDBCSampler
    """
    from direct_insert_write.sampler_generator import (
        DirectInsertGenerationError,
        generate_relational_table_init_sampler,
    )

    table_name = spec["table_name"]
    columns: List[str] = list(spec["columns"])
    total_rows: int = int(spec["total_rows"])
    batch_lines: int = int(spec.get("batch_lines") or _DEFAULT_REL_BATCH_LINES)
    rel_col_seed_files: List[str] = list(spec["rel_col_seed_files"])
    column_types: Optional[List[str]] = spec.get("column_types")

    cfg = generate_relational_table_init_sampler(
        table_name=table_name,
        columns=columns,
        total_rows=total_rows,
        batch_lines=batch_lines,
        rel_col_seed_files=rel_col_seed_files,
        column_types=column_types,
    )

    loop_count = int(cfg["loop_count"])
    pre_script = cfg["preprocessor_script"]
    sampler_name = cfg["name"]

    # LoopController element wrapping ``main_controller`` semantics.
    loop_props = [
        bool_prop("LoopController.continue_forever", "false"),
        string_prop("LoopController.loops", str(loop_count)),
    ]
    loop_main = element_prop(
        name="ThreadGroup.main_controller",
        element_type="LoopController",
        testname="Loop Controller",
        props=loop_props,
    )
    loop_ctrl = make_element(
        "GenericController",
        name=f"Loop Controller for {table_name}",
        testname=f"Loop Controller for {table_name}",
        attributes={"guiclass": "LoopControlPanel", "testclass": "LoopController"},
        children=[loop_main],
    )

    # PreProcessor that fills param_N from seed files.
    prep, prep_hash = jsr223_preprocessor_element(
        name=f"{sampler_name}_relprep",
        script=pre_script,
        script_language="groovy",
        testname=f"{sampler_name}_relprep",
        enabled=True,
    )

    # JDBCSampler that runs Prepared Update Statement per loop iteration.
    sampler, samp_hash = jdbc_sampler_element(
        name=sampler_name,
        query=cfg["sql"],
        data_source=cfg["data_source"],
        query_type=cfg["query_type"],
        query_arguments=cfg["query_arguments"],
        query_arguments_types=cfg["query_arguments_types"],
        testname=sampler_name,
    )

    inner = hash_tree(prep, prep_hash, sampler, samp_hash)
    # Keep ``loop_ctrl`` and ``inner`` as siblings inside the parent
    # SetupThreadGroup hashTree. JMeter's XStream parser rejects a
    # ``<hashTree>`` mounted as a child of ``<GenericController>``
    # (ClassCastException: ListedHashTree → JMeterProperty), so the
    # loop boundary must ride on a sibling hashTree at the same
    # hierarchical level.
    return [loop_ctrl, inner]


# ---------------------------------------------------------------------------
# REST 路径：HTTP DDL SetupTG（Login + DDL pre-create）
# ---------------------------------------------------------------------------


# JSR223 Assertion 脚本模板：KaiwuDB RESTful DDL API 响应包 JSON 形如
# ``{"code": 0, "message": "..."}``；非零 code 即视为 DDL 失败。
_DDL_RESPONSE_ASSERTION_SCRIPT = (
    'if (prev.getResponseDataAsString().contains(\'"code":0\')) '
    'return; else throw new RuntimeException('
    '"DDL failed: " + prev.getResponseDataAsString())'
)


def _build_json_extractor_element(name: str, testname: str) -> Any:
    """构造 ``<JSONPostProcessor>`` 元素，从响应 JSON 抽取 ``$.token`` → ``${token}``。

    返回的 Element 必须由调用方紧随一个配对 ``<hashTree/>`` 兄弟节点。
    """
    return make_element(
        "JSONPostProcessor",
        name=name,
        testname=testname,
        attributes={
            "guiclass": "JSONPostProcessorGui",
            "testclass": "JSONPostProcessor",
            "enabled": "true",
        },
        children=[
            string_prop("JSONPostProcessor.referenceNames", "token"),
            string_prop("JSONPostProcessor.jsonPathExprs", "$.token"),
            string_prop("JSONPostProcessor.match_numbers", "1"),
        ],
    )


def _build_jsr223_postprocessor_element(
    name: str, testname: str, script: str
) -> Any:
    """构造 ``<JSR223PostProcessor>`` 元素（scriptLanguage=groovy）。"""
    return make_element(
        "JSR223PostProcessor",
        name=name,
        testname=testname,
        attributes={
            "guiclass": "TestBeanGUI",
            "testclass": "JSR223PostProcessor",
            "enabled": "true",
        },
        children=[
            string_prop("cacheKey", "true"),
            string_prop("filename", ""),
            string_prop("parameters", ""),
            string_prop("script", script),
            string_prop("scriptLanguage", "groovy"),
        ],
    )


def _build_jsr223_assertion_element(
    name: str, testname: str, script: str
) -> Any:
    """构造 ``<JSR223Assertion>`` 元素（scriptLanguage=groovy）。"""
    return make_element(
        "JSR223Assertion",
        name=name,
        testname=testname,
        attributes={
            "guiclass": "TestBeanGUI",
            "testclass": "JSR223Assertion",
            "enabled": "true",
        },
        children=[
            string_prop("cacheKey", "true"),
            string_prop("filename", ""),
            string_prop("parameters", ""),
            string_prop("script", script),
            string_prop("scriptLanguage", "groovy"),
        ],
    )


def generate_ddl_setup_http_thread_group(
    ddl_statements: List[str],
    *,
    name: str = "DDL Setup (REST)",
    num_threads: int = 1,
    rel_init_specs: Optional[Sequence[Dict[str, Any]]] = None,
    rest_api_config: Dict[str, Any],
) -> List:
    """Build a SetupThreadGroup that runs Login → (DDL pre-create loop) → rel-init。

    与 ``generate_ddl_setup_thread_group(...)`` 并列、专供 RESTful 写入路径
    使用（``mode: schemaless``；§5 锁定 enum 复用 `schemaless`）。复用现有 ``setup_thread_group_element(...)``
    外壳，仅把 ``jdbc_sampler_element`` 替换为 ``http_request_sampler_element``，
    并在 Login sampler 之后追加 JSON Extractor + JSR223 PostProcessor 把
    token 写入 JMeter 单例 props，供后续 TG（DDL / Write / Query）通过
    ``${__property(rest_token)}`` 共享。

    Parameters
    ----------
    ddl_statements:
        DDL SQL 字符串列表（由 ``DDLGenerator.generate(...)`` 产出）。当
        ``rest_api_config['pre_create_tables']`` 为 ``True`` 时，每条 DDL
        生成一个 POST sampler；否则跳过 DDL sampler，仅保留 Login + token 传播。
    name:
        SetupThreadGroup 显示名（默认 ``"DDL Setup (REST)"``）。
    num_threads:
        线程数（默认 1）。
    rel_init_specs:
        关系表初始化 spec 列表；非空时按现有 ``_build_rel_init_subtree`` 装配
        （与 JDBC 路径完全相同）。
    rest_api_config:
        必填字段：
          - ``login_url_path: str``
          - ``ddl_url_path: str``
          - ``login_user: str``
          - ``login_password: str``
          - ``ca_cert_path: str``（TLS 模式强制）
          - ``pre_create_tables: bool``

        ``ca_cert_path`` 缺失时，立即抛 ``RestConfigError``
        （fail-fast，proposal §1.1 场景 1；2026-07-27 起 schemaless Login
        仅支持 TLS，insecure 路径移除）。

    Returns
    -------
    ``[SetupThreadGroup, hashTree]``，hashTree 内依次包含 Login sampler →
    JSON Extractor → JSR223 PostProcessor → DDL sampler 列表（pre_create_tables
    时）→ rel-init 子树（rel_init_specs 非空时）。
    """
    # 1) fail-fast：TLS 必须带 ca_cert_path（2026-07-27 起 insecure 路径移除：
    # schemaless Login 需非空密码用户，非空密码用户只能通过安全模式创建）。
    ca_cert_path = rest_api_config.get("ca_cert_path")
    if not ca_cert_path:
        raise RestConfigError.missing_ca_cert()

    pre_create_tables = bool(rest_api_config.get("pre_create_tables", False))
    # 暴露 ca_cert_path 为 UDV（`${__P(rest_api.ca_cert_path,EMPTY)}`），避免把
    # fixture 字面路径（相对路径）烤进 JMX —— 跨环境 / cert 路径变更无需重生成。
    # 默认空 → 用户必须 `-Jrest_api.ca_cert_path=/abs/path/to/ca.crt`。
    ssl_context: Optional[str] = "${__P(rest_api.ca_cert_path,)}"
    protocol = "https"

    # 2) Login sampler：GET login_url_path + Authorization: Basic base64(user:pass)。
    login_user = rest_api_config["login_user"]
    login_password = rest_api_config["login_password"]
    login_path = rest_api_config["login_url_path"]
    login_basic = "Basic " + base64.b64encode(
        f"{login_user}:{login_password}".encode()
    ).decode()

    login_sampler, login_hash = http_request_sampler_element(
        method="GET",
        path=login_path,
        headers={"Authorization": login_basic},
        body="",
        ssl_context=ssl_context,
        name="DDL Login",
        testname="DDL Login",
    )
    # 注入 domain / port / protocol（http_request_sampler_element 不产出这三项
    # —— utils ref doc R1 锁定的 caller 约定，否则 JMeter 报
    # "URI does not specify a valid host name: http:/restapi/ddl"）。
    login_sampler.insert(0, string_prop("HTTPSampler.domain", "${__P(rest_api.hostname,127.0.0.1)}"))
    login_sampler.insert(0, string_prop("HTTPSampler.port", "${__P(rest_api.http_port,8080)}"))
    login_sampler.insert(0, string_prop("HTTPSampler.protocol", protocol))

    # 3) JSON Extractor（PostProcessor 角色）：$.token → ${token}。
    json_extractor = _build_json_extractor_element(
        name="REST Token Extractor",
        testname="REST Token Extractor",
    )

    # 4) JSR223 PostProcessor：把 JSON Extractor 抽出的 ${token} 写到 JMeter
    # 单例 props，后续 TG 通过 ${__property(rest_token)} 共享。必须是 Groovy
    # 代码——${__setProperty(...)} 函数表达式会被 JMeter 当空脚本（报
    # "Both script file and script text are empty"）。
    #
    # §6.4.2：守卫 null/empty —— 当 JSON Extractor 没抽到（Login 失败或响应
    # 不含 $.token），vars.get("token") 返 null；裸 props.put(K, null) 在
    # JMeter Groovy 上下文要么抛 NPE 要么字符串化为 "null"，下游
    # ${__property(rest_token)} 解析为 "Basic null" 或 "Basic "，DDL-2
    # （create ts table with primary tags）服务端强校验触发
    # {"code":-1,"desc":"can not find Basic attribute"}。DDL-1（ts database）
    # 服务端弱校验侥幸 201 蒙混。守卫保证仅写入非空值。
    setprop_script = (
        'def t = vars.get("token")\n'
        'if (t != null && t.length() > 0) {\n'
        '    props.put("rest_token", t)\n'
        '}\n'
        'return'
    )
    setprop_postproc = _build_jsr223_postprocessor_element(
        name="REST Token Set Property",
        testname="REST Token Set Property",
        script=setprop_script,
    )

    children: List = [login_sampler, login_hash, json_extractor, empty_hash_tree(),
                      setprop_postproc, empty_hash_tree()]

    # 5) DDL pre-create HTTP samplers（pre_create_tables=true 时）。
    ddl_url_path = rest_api_config["ddl_url_path"]
    ddl_auth_header = {"Authorization": "Basic ${__property(rest_token)}"}
    if pre_create_tables:
        for i, ddl in enumerate(ddl_statements):
            ddl_name = f"DDL-{i + 1}"
            ddl_sampler, ddl_hash = http_request_sampler_element(
                method="POST",
                path=ddl_url_path,
                headers=ddl_auth_header,
                body=ddl,
                ssl_context=ssl_context,
                name=ddl_name,
                testname=ddl_name,
            )
            # 同 Login：caller 必须注入 domain / port / protocol。
            ddl_sampler.insert(0, string_prop("HTTPSampler.domain", "${__P(rest_api.hostname,127.0.0.1)}"))
            ddl_sampler.insert(0, string_prop("HTTPSampler.port", "${__P(rest_api.http_port,8080)}"))
            ddl_sampler.insert(0, string_prop("HTTPSampler.protocol", protocol))
            # JSR223 Assertion 作为 DDL sampler 的子断言，挂在同一 hashTree 内。
            ddl_assert = _build_jsr223_assertion_element(
                name=f"{ddl_name}_assert",
                testname=f"{ddl_name}_assert",
                script=_DDL_RESPONSE_ASSERTION_SCRIPT,
            )
            ddl_hash.append(ddl_assert)
            ddl_hash.append(empty_hash_tree())

            children.extend([ddl_sampler, ddl_hash])

    # 6) rel-init 子树（rel_init_specs 非空时，与 JDBC 路径共用 _build_rel_init_subtree）。
    for spec in rel_init_specs or []:
        children.extend(_build_rel_init_subtree(spec))

    # 7) SetupThreadGroup 外壳。
    stg, stg_hash = setup_thread_group_element(
        name=name,
        testname=name,
        num_threads=num_threads,
        ramp_time=1,
        duration="${test_duration}",
        delay=0,
        loops=1,
        scheduler=True,
        children=children,
    )
    return [stg, stg_hash]

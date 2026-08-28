"""TestPlan and UserDefinedVariables generators."""

from __future__ import annotations

import re
from typing import List, Optional

from config_parser.models import ConnConfig
from utils.xml_helpers import (
    argument_element,
    bool_prop,
    collection_prop,
    element_prop,
    string_prop,
    test_plan_element,
)


class JmxGenerationError(Exception):
    """Raised when JMX generation fails."""


def _validate_var_name(key: str) -> str:
    """Reject empty or non-identifier keys as JMeter variable names."""
    if not key or not key.strip():
        raise ValueError("variable name must not be empty")
    if not re.match(r"[a-zA-Z_][a-zA-Z0-9_]*$", key):
        raise ValueError(f"invalid JMeter variable name: {key!r}")
    return key


# ---------------------------------------------------------------------------
# UserDefinedVariables
# ---------------------------------------------------------------------------

def generate_user_defined_variables(
    conn_config: ConnConfig,
    *,
    seed_dir: Optional[str] = None,
    login_user: Optional[str] = None,
    login_password: Optional[str] = None,
) -> List:
    """Build Arguments + hashTree elements for connection configuration.

    Parameters
    ----------
    conn_config:
        Connection configuration from ``TestConfig``.
    seed_dir:
        Absolute path to the seed CSV directory baked at generation time
        (typically ``<output_dir>/seeds``). Goes through
        ``${__P(seed_dir,<default>)}`` so a launching pipeline can
        override it via ``-J seed_dir=<path>`` on the JMeter CLI (or
        via ``user.properties`` if the pipeline still loads one).
        Samplers read the resolved value via ``vars.get('seed_dir')``,
        which the UDV config element populates from the evaluated
        ``${__P(...)}`` expression. ``None`` (default for non-skeleton
        callers) skips emitting the ``seed_dir`` UDV.

    Returns
    -------
    A list containing the ``Arguments`` element and its paired ``<hashTree/>``.
    The ``Arguments`` element encloses all conn_config fields as
    ``<elementProp>`` entries wrapped in a ``<collectionProp>``.

    Raises
    ------
    ValueError
        When a variable name is not a valid JMeter identifier.
    """
    # F-15 (2026-07-21): operational UDV defaults go through
    # ``${__P(name,default)}`` so ``-J<name>=value`` on the JMeter CLI
    # overrides the YAML default. Previously ``test_duration`` was
    # hardcoded with the YAML value (``str(conn_config.test_duration)``),
    # so ``-Jtest_duration=60`` was silently ignored (UDV scope beats
    # JMeter property scope).
    #
    # Credentials (``db_url``/``db_username``/``db_password``) are
    # kept as literal YAML values in the UDV — operators override
    # them via ``-Jdb_url=...`` / ``-Jdb_password=...`` at the CLI,
    # and a JSR223 PreProcessor emitted right after the UDV copies
    # the matching JMeter properties into the JMeterVariables so the
    # downstream JDBC sampler sees the override (see
    # :func:`generate_credential_override_preprocessor`).
    #
    # We avoid ``${__P(db_password,'')}`` for empty-default credentials
    # because JMeter's __P function parses its default as a JMeter
    # expression — but ``''`` (the would-be empty literal) leaves the
    # value as the literal two-character string ``''`` (with
    # apostrophes around it), which the JDBC driver then sends as the
    # password and trips cluster auth.
    fields = {
        # F-15 + user feedback 2026-07-21: every UDV default goes
        # through ``${__P(name,default)}`` so ``-J<name>=value`` on
        # the JMeter CLI overrides the YAML default. The default
        # value is the raw literal — NO single-quote wrapping. The
        # reference at ``scenarios/shig/plans/plan.jmx`` uses the
        # same form (``${__P(user.db.url,jdbc:kaiwudb://...)}``).
        #
        # For ``db_password`` with an empty YAML default, leave the
        # trailing comma with no second arg (``${__P(db_password,)}``):
        # JMeter treats the missing default as empty string, so an
        # unset ``-Jdb_password=`` keeps the YAML's empty default
        # (and avoids the auth trip where ``${__P(db_password)}``
        # defaults to the literal ``"1"``).
        "db_url": f"${{__P(db_url,{conn_config.db_url})}}",
        "db_username": f"${{__P(db_username,{conn_config.db_username})}}",
        "db_password": f"${{__P(db_password,{conn_config.db_password})}}",
        "conn_pool_size": f"${{__P(conn_pool_size,{conn_config.conn_pool_size})}}",
        # multi-end tasks §1.1+§1.2: device_* fields use ${__P(...)} so that
        # operators can override per JMeter instance via `-Jdevice_start=N`,
        # `-Jdevice_per_thread=N` without editing the JMX file.
        "device_start": "${__P(device_start,1)}",
        "device_per_thread": "${__P(device_per_thread,1)}",
        "test_duration": f"${{__P(test_duration,{conn_config.test_duration})}}",
        "write_throughput": "${__P(write_throughput,120)}",  # default 120 samples/min
    }
    # F-16 (2026-08-20): expose ``seed_dir`` as a UDV so the absolute path
    # baked at generation time (``output_dir/seeds``) is the default, but
    # the launching pipeline can override it via ``-J seed_dir=<path>``
    # on the JMeter CLI. Query TG and Setup TG both read it via
    # ``vars.get('seed_dir')``; the UserDefinedVariables config element
    # populates that JMeterVariable from the evaluated ``${__P(seed_dir,default)}``
    # expression.
    #
    # Older pipelines that set ``user.seed_conf_path`` directly were
    # silently broken because ``vars.get('seed_dir')`` does NOT see
    # JMeter properties (only JMeter variables), so it never reached the
    # samplers and they fell back to the literal string ``'seeds'``
    # resolved against the JMeter working directory — usually wrong on
    # shared svt-test-server boxes where multiple builds run in
    # parallel.
    if seed_dir is not None:
        fields["seed_dir"] = f"${{__P(seed_dir,{seed_dir})}}"

    # Login auth (mode=schemaless only): expose ``login_user`` / ``login_password``
    # as UDVs so the DDL Login PreProcessor can compute the runtime
    # ``Basic`` Authorization header from ``vars.get`` rather than baking
    # base64(user:pass) at generation time.  Same ``${__P(name,default)}``
    # form as the conn fields above; pass ``-Jlogin_user=...`` /
    # ``-Jlogin_password=...`` on the JMeter CLI to override.
    if login_user is not None:
        fields["login_user"] = f"${{__P(login_user,{login_user})}}"
    if login_password is not None:
        fields["login_password"] = f"${{__P(login_password,{login_password})}}"

    arg_props: List = []
    for key, value in fields.items():
        validated = _validate_var_name(key)
        arg_props.append(
            element_prop(
                name=validated,
                element_type="Argument",
                testname=validated,
                props=[
                    string_prop("Argument.name", validated),
                    string_prop("Argument.value", value),
                    string_prop("Argument.metadata", "="),
                ],
            )
        )

    collection = collection_prop(
        "Arguments.arguments",
        children=arg_props,
    )

    args, args_hash = argument_element(
        name="UserDefinedVariables",
        testname="User Defined Variables",
        guiclass="ArgumentsPanel",
        testclass="Arguments",
        props=[collection],
    )
    return [args, args_hash]


# ---------------------------------------------------------------------------
# TestPlan
# ---------------------------------------------------------------------------

def generate_test_plan(*, comments: str = "") -> List:
    """Build a TestPlan element and its paired hashTree.

    Parameters
    ----------
    comments:
        Descriptive comment inserted in the TestPlan.

    Returns
    -------
    A list containing the ``TestPlan`` element and its paired
    ``<hashTree/>`` (which will hold all child components).
    """
    props = [
        bool_prop("TestPlan.tearDown_on_shutdown", "true"),
        bool_prop("TestPlan.functional_mode", "false"),
        bool_prop("TestPlan.serialize_threadgroups", "false"),
        element_prop(
            name="TestPlan.user_defined_variables",
            element_type="Arguments",
            testname="User Defined Variables",
            props=[
                collection_prop("Arguments.arguments"),
            ],
        ),
    ]
    if comments:
        props.insert(0, string_prop("TestPlan.comments", comments))

    return list(test_plan_element(
        name="TestPlan",
        testname="KaiwuDB SVT TestPlan",
        props=props,
    ))

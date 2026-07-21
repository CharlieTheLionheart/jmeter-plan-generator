"""TestPlan and UserDefinedVariables generators."""

from __future__ import annotations

import re
from typing import List

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

def generate_user_defined_variables(conn_config: ConnConfig) -> List:
    """Build Arguments + hashTree elements for connection configuration.

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
    # Credentials (``db_url``/``db_username``/``db_password``) are NOT
    # exposed via ``${__P(...)}`` for two reasons:
    #   1. ``${__P(name)}`` with no default returns ``"1"`` (literal),
    #      not empty — so ``db_password = ${__P(db_password,)}`` would
    #      become the password ``"1"`` and trip cluster auth.
    #   2. Credentials in plaintext at the CLI surface is a poor
    #      security posture; CI should bake them into the JMX instead.
    fields = {
        "db_url": str(conn_config.db_url),
        "db_username": str(conn_config.db_username),
        "db_password": str(conn_config.db_password),
        "conn_pool_size": f"${{__P(conn_pool_size,{conn_config.conn_pool_size})}}",
        # multi-end tasks §1.1+§1.2: device_* fields use ${__P(...)} so that
        # operators can override per JMeter instance via `-Jdevice_start=N`,
        # `-Jdevice_per_thread=N` without editing the JMX file.
        "device_start": "${__P(device_start,1)}",
        "device_per_thread": "${__P(device_per_thread,1)}",
        "test_duration": f"${{__P(test_duration,{conn_config.test_duration})}}",
        "write_throughput": "${__P(write_throughput,120)}",  # default 120 samples/min
    }

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

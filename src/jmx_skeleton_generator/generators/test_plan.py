"""TestPlan and UserDefinedVariables generators."""

from __future__ import annotations

import re
from typing import List

from config_parser.models import ConnConfig
from utils.xml_helpers import (
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
    fields = {
        "db_url": str(conn_config.db_url),
        "db_username": str(conn_config.db_username),
        "db_password": str(conn_config.db_password),
        "conn_pool_size": str(conn_config.conn_pool_size),
        "device_start": str(conn_config.device_start),
        "test_duration": str(conn_config.test_duration),
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

    args, args_hash = test_plan_element(
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

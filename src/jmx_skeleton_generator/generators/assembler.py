"""JMX assembler and writer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from xml.etree import ElementTree as ET

from utils.xml_helpers import (
    empty_hash_tree,
    hash_tree,
    write_jmx,
)


JMETER_NS = "http://jmeter.apache.org/"
ET.register_namespace("", JMETER_NS)


class JmxGenerationError(Exception):
    """Raised when JMX generation or serialisation fails."""


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

def _q(tag: str) -> str:
    return f"{{{JMETER_NS}}}{tag}"


class JMXAssembler:
    """Assemble a complete JMX element tree from sub-components.

    The JMX format requires a strict alternating structure:
    component, <hashTree/>, component, <hashTree/>, ...

    The root of the JMX file is always:
      <jmeterTestPlan version="1.2" properties="...">
        <hashTree>
          [TestPlan]
          <hashTree>
            [Arguments (UDV)]
            <hashTree/>
            [JDBCDataSource]
            <hashTree/>
            [SetupThreadGroup]
            <hashTree>
              [JDBCSampler]
              <hashTree/>
            </hashTree>
            [Write ThreadGroups]
            ...
            [Query ThreadGroups]
            ...
          </hashTree>
        </hashTree>
      </jmeterTestPlan>
    """

    def __init__(self):
        self._elements: List[ET.Element] = []

    def add(self, elem: ET.Element) -> "JMXAssembler":
        """Append a single element (e.g. a component or hashTree)."""
        self._elements.append(elem)
        return self

    def add_many(self, elems: List[ET.Element]) -> "JMXAssembler":
        """Extend with a flat list of elements."""
        self._elements.extend(elems)
        return self

    def assemble(
        self,
        test_plan_elem: ET.Element,
        test_plan_hash: ET.Element,
        udv_elements: List[ET.Element],
    ) -> ET.Element:
        """Build the complete JMX element tree.

        Parameters
        ----------
        test_plan_elem:
            The ``<TestPlan>`` element.
        test_plan_hash:
            The paired ``<hashTree/>`` that will contain all children
            under the TestPlan.
        udv_elements:
            Flat list of ``[Arguments, hashTree/]`` elements.

        Returns
        -------
        The root ``<jmeterTestPlan>`` element.
        """
        # Root
        root = ET.Element(_q("jmeterTestPlan"), {"version": "1.2", "properties": "5.0"})
        top_hash = hash_tree()
        root.append(top_hash)

        # TestPlan and its hashTree are siblings, both children of root's hashTree
        top_hash.append(test_plan_elem)

        # All child components go inside test_plan_hash
        test_plan_hash.append(udv_elements[0])  # Arguments
        test_plan_hash.append(udv_elements[1])  # hashTree/
        # any additional top-level components go here
        for elem in self._elements:
            test_plan_hash.append(elem)

        top_hash.append(test_plan_hash)

        return root


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class JMXWriter:
    """Serialise an assembled JMX element tree to a file."""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)

    def write(
        self,
        root: ET.Element,
        filename: str = "test_plan.jmx",
        *,
        encoding: str = "UTF-8",
    ) -> Path:
        """Write the JMX tree to a file.

        Parameters
        ----------
        root:
            Assembled ``<jmeterTestPlan>`` root element.
        filename:
            Output filename.
        encoding:
            Character encoding.

        Returns
        -------
        Absolute path to the written file.

        Raises
        ------
        JmxGenerationError
            When the output directory cannot be created or writing fails.
        """
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise JmxGenerationError(f"cannot create output directory {self.output_dir}: {exc}") from exc

        path = self.output_dir / filename
        try:
            write_jmx(root, str(path), encoding=encoding)
        except OSError as exc:
            raise JmxGenerationError(f"cannot write JMX file {path}: {exc}") from exc

        return path.resolve()

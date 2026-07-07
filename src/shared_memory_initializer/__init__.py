"""Shared memory initializer for JMeter test plans.

This module generates Groovy scripts and JSR223PreProcessor XML components
that load row seed data from CSV files into JMeter shared memory (props).

Data Structure:
    - __SHARED_MEM_{db}.{table}: List[List[Any]] (row-first 2D array)
    - __SHARED_MEM_{db}.{table}_columns: List[String] (column names in fixed order)

CSV Format (from seed-data-generator):
    - First line: column names
    - Subsequent lines: data rows
    - "null" string in CSV → Groovy null object

Usage:
    from shared_memory_initializer import SharedMemoryInitializerGenerator

    generator = SharedMemoryInitializerGenerator()
    preprocessor, hash_tree = generator.generate_for_table("tsdb", "t_table", "/path/to/seeds/tsdb/t_table.csv")
"""

from shared_memory_initializer.shared_memory_initializer import (
    SharedMemoryInitializerGenerator,
)

__all__ = ["SharedMemoryInitializerGenerator"]

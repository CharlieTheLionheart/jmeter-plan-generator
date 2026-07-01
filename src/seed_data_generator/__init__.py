"""Seed data generator for KaiwuDB SVT test plan generator.

Supports:

- Numeric ``val_range`` expressions: ``>=n``, ``<=n``, ``[a,b]``, ``(a,b)``
- Regex-generated strings (via ``rstr``)
- Enum cycling (always cycles, no truncation)
- Foreign-key reference sampling from pre-generated seed files
- NULL injection using ``floor(null_rate * seed_num)``
- Column seed files (no header, one value per line): ``seeds/{db}/{table}/{index}_{col_name}.csv``
- Row seed aggregate CSV files (with header): ``seeds/{db}/{table}.csv``
- First Primary Tag column: no seed file generated; ``${device_code}`` placeholder injected into row aggregate at runtime

NULL values are written as the literal string ``null`` and are randomly
scattered through each column seed list.
"""

from seed_data_generator.adapter import ValueDomain, classify_val_range
from seed_data_generator.orchestrator import cleanup_table, generate_seeds
from seed_data_generator.adapter import SeedGenError

__all__ = [
    "classify_val_range",
    "cleanup_table",
    "generate_seeds",
    "SeedGenError",
    "ValueDomain",
]

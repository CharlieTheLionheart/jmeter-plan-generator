## ADDED Requirements

### Requirement: Create JMeter XML elements
The system SHALL provide utility functions to create JMeter-specific XML elements.

#### Scenario: Create a basic JMeter element
- **WHEN** a module calls `create_element(tag, attrib=None)`
- **THEN** the system SHALL return an `xml.etree.ElementTree.Element` with the given tag and attributes

#### Scenario: Add a HashTree node
- **WHEN** a module needs to add a JMeter `<HashTree>` child
- **THEN** the system SHALL provide `add_hash_tree(parent)` which appends an empty `<HashTree>` element and returns it

#### Scenario: Add a stringProp element
- **WHEN** a module calls `add_string_prop(parent, name, value)`
- **THEN** the system SHALL append a `<stringProp name="{name}"{value}</stringProp>` element under `parent`

#### Scenario: Add a boolProp element
- **WHEN** a module calls `add_bool_prop(parent, name, value)`
- **THEN** the system SHALL append a `<boolProp name="{name}"{value}</boolProp>` element under `parent`

#### Scenario: Serialize XML tree to string
- **WHEN** a module calls `to_string(element)`
- **THEN** the system SHALL return a UTF-8 string representation of the XML tree with consistent indentation

### Requirement: Parse comparison val_range expressions
The system SHALL parse `val_range` expressions that use comparison operators.

#### Scenario: Parse greater-than-or-equal expression
- **WHEN** `val_range` is `>=1`
- **THEN** the system SHALL set `kind` to `comparison`
- **THEN** `operator` SHALL be `gte`
- **THEN** `lower_bound` SHALL be `1.0`
- **THEN** `upper_bound` SHALL be unbounded

#### Scenario: Parse less-than-or-equal expression
- **WHEN** `val_range` is `<=100`
- **THEN** the system SHALL set `kind` to `comparison`
- **THEN** `operator` SHALL be `lte`
- **THEN** `upper_bound` SHALL be `100.0`
- **THEN** `lower_bound` SHALL be unbounded

#### Scenario: Parse greater-than expression
- **WHEN** `val_range` is `>0`
- **THEN** the system SHALL set `kind` to `comparison`
- **THEN** `operator` SHALL be `gt`
- **THEN** `lower_bound` SHALL be `0.0` and exclusive

#### Scenario: Parse less-than expression
- **WHEN** `val_range` is `<10`
- **THEN** the system SHALL set `kind` to `comparison`
- **THEN** `operator` SHALL be `lt`
- **THEN** `upper_bound` SHALL be `10.0` and exclusive

#### Scenario: Parse equal expression
- **WHEN** `val_range` is `=5`
- **THEN** the system SHALL set `kind` to `comparison`
- **THEN** `operator` SHALL be `eq`
- **THEN** `lower_bound` and `upper_bound` SHALL both be `5.0`

### Requirement: Parse interval val_range expressions
The system SHALL parse interval notation expressions.

#### Scenario: Parse closed interval
- **WHEN** `val_range` is `[1,100]`
- **THEN** the system SHALL set `kind` to `interval`
- **THEN** `lower_bound` SHALL be `1.0` and `lower_inclusive=true`
- **THEN** `upper_bound` SHALL be `100.0` and `upper_inclusive=true`

#### Scenario: Parse open interval
- **WHEN** `val_range` is `(1,100)`
- **THEN** the system SHALL set `kind` to `interval`
- **THEN** `lower_inclusive=false` and `upper_inclusive=false`

#### Scenario: Parse half-open intervals
- **WHEN** `val_range` is `[1,100)`
- **THEN** `lower_inclusive=true` and `upper_inclusive=false`
- **WHEN** `val_range` is `(1,100]`
- **THEN** `lower_inclusive=false` and `upper_inclusive=true`

### Requirement: Parse regex val_range expressions
The system SHALL identify regex-style `val_range` expressions.

#### Scenario: Parse regex pattern
- **WHEN** `val_range` is `^[一-鿿a-zA-Z0-9-_]{2,10}$`
- **THEN** the system SHALL set `kind` to `regex`
- **THEN** `regex_pattern` SHALL be the original pattern string

### Requirement: Parse enum val_range expressions
The system SHALL parse enumeration expressions.

#### Scenario: Parse enum values
- **WHEN** `val_range` is `enum:M1,M2,M3`
- **THEN** the system SHALL set `kind` to `enum`
- **THEN** `enum_values` SHALL be `["M1", "M2", "M3"]`

#### Scenario: Preserve enum value order
- **WHEN** `val_range` is `enum:A,B,C`
- **THEN** the system SHALL preserve the order `["A", "B", "C"]`

### Requirement: Parse foreign key reference expressions
The system SHALL parse `ref:` foreign key reference expressions.

#### Scenario: Parse valid reference
- **WHEN** `val_range` is `ref:iot_metadata.t_workshop.pk_int8_1`
- **THEN** the system SHALL set `kind` to `ref`
- **THEN** `ref_db` SHALL be `iot_metadata`
- **THEN** `ref_table` SHALL be `t_workshop`
- **THEN** `ref_column` SHALL be `pk_int8_1`

#### Scenario: Preserve raw reference string
- **WHEN** a reference is parsed
- **THEN** the system SHALL keep the original expression in `raw`

### Requirement: Expose parser classification helpers
The system SHALL provide convenience predicates for checking the expression kind.

#### Scenario: Check expression kind
- **WHEN** a `ValRange` result has `kind=enum`
- **THEN** `is_enum()` SHALL return `True`
- **THEN** `is_ref()` SHALL return `False`
- **THEN** `is_numeric_range()` SHALL return `False`

### Requirement: Handle unknown val_range expressions
The system SHALL classify unsupported expressions as `unknown`.

#### Scenario: Detect unsupported expression
- **WHEN** `val_range` is an empty string or does not match any known format
- **THEN** the system SHALL set `kind` to `unknown`
- **THEN** the system SHALL not raise an exception during parsing

### Requirement: Provide PreProcessor helper functions
The system SHALL provide utility functions for generating JSR223PreProcessor scripts in write strategies.

**Note**: Shared memory initialization and loading logic is handled by the `shared-memory-initializer` module. This module provides helper functions for data processing and script generation.

#### Scenario: Clone rows to avoid modifying shared memory
- **WHEN** calling `clone_rows(rows)`
- **THEN** the system SHALL generate code to use `row.clone()` for each row
- **THEN** the system SHALL return a new list without affecting the original shared memory

#### Scenario: Calculate timestamps for each row
- **WHEN** calling `calculate_timestamps(base_time, batch_seq, ms_step, batch_lines)`
- **THEN** the system SHALL generate code using formula `base_time + batch_seq * ms_step + i * (ms_step / batch_lines)`
- **THEN** the system SHALL convert to `java.sql.Timestamp`
- **THEN** the system SHALL return a list of timestamp values

#### Scenario: Calculate device number for multi-end coordination
- **WHEN** calling `calculate_device_number(device_start, thread_num, device_per_thread, row_index)`
- **THEN** the system SHALL generate code `device_start + thread_num * device_per_thread + (row_index % device_per_thread)`
- **THEN** the system SHALL return the calculated device number

#### Scenario: Replace placeholder with device identifier
- **WHEN** calling `replace_placeholder(value, device_number)`
- **THEN** the system SHALL generate code to replace `${device_code}` with `device_{device_number}`
- **THEN** the system SHALL return the replaced value

#### Scenario: Generate PreProcessor script template
- **WHEN** calling `generate_preprocessor_template(strategy_specific_parts)`
- **THEN** the system SHALL generate a complete JSR223PreProcessor Groovy script
- **THEN** the system SHALL integrate strategy-specific parts (SQL templates, batch size, etc.)
- **THEN** the system SHALL return a script compatible with JMeter JSR223PreProcessor

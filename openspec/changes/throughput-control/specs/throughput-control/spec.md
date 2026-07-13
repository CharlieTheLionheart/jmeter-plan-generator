## ADDED Requirements

### Requirement: Generate ConstantThroughputTimer for write thread groups
The system SHALL generate a ConstantThroughputTimer for each write thread group to control write throughput. The timer's `throughput` property SHALL reference the JMeter variable `${write_throughput}` defined in `User Defined Variables`.

#### Scenario: Generate timer for write thread group
- **WHEN** generating a write thread group with `write_throughput=60` (set in UDV)
- **THEN** the system SHALL generate a `ConstantThroughputTimer` element
- **THEN** the `throughput` property SHALL be `${write_throughput}`
- **THEN** the `calcMode` property SHALL be `0` (This thread only)
- **THEN** each thread SHALL independently target `60` samples per minute

#### Scenario: Default write throughput UDV
- **WHEN** the generated JMX is loaded without overriding the `write_throughput` UDV
- **THEN** `${write_throughput}` SHALL default to `120` (i.e. 2 samples per second per thread)
- **THEN** each thread SHALL independently target `120` samples per minute

### Requirement: Generate ConstantThroughputTimer for query thread groups with fixed value
The system SHALL generate a ConstantThroughputTimer for each query thread group whose `throughput` property is the literal string form of the per-query `QueryConfig.throughput` value. The value SHALL NOT be routed through a JMeter UDV variable.

#### Scenario: Generate timer for query thread group
- **WHEN** generating a query thread group with `QueryConfig.throughput=4`
- **THEN** the system SHALL generate a `ConstantThroughputTimer` element
- **THEN** the `throughput` property SHALL be the literal string `"4"` (no `${...}` wrapping)
- **THEN** the `calcMode` property SHALL be `0` (This thread only)
- **THEN** each thread SHALL independently target `4` samples per minute

#### Scenario: Two queries with different throughput values get distinct fixed timers
- **WHEN** two `QueryConfig` entries have `throughput=4` and `throughput=12` respectively
- **THEN** each generated thread group's timer SHALL embed its own throughput literal (`"4"` vs `"12"`)
- **THEN** changing one query's `throughput` SHALL NOT affect the other query's timer

#### Scenario: No `${query_throughput}` UDV is generated
- **WHEN** the JMX is rendered end-to-end
- **THEN** the `User Defined Variables` element SHALL NOT contain a `query_throughput` entry
- **THEN** query thread group timers SHALL NOT reference any `${query_throughput}` variable

### Requirement: Use calcMode 0 for per-thread targeting
The system SHALL set the `calcMode` property to `0` for both write and query ConstantThroughputTimer elements.

#### Scenario: Set calcMode in timer
- **WHEN** generating a ConstantThroughputTimer (write or query)
- **THEN** the system SHALL set `<intProp name="calcMode">0</intProp>`
- **THEN** each thread SHALL independently target the specified throughput value

### Requirement: Reject non-positive throughput at config parse time
The system SHALL reject any `WriteConfig` or `QueryConfig` whose `throughput` is `<= 0` during configuration parsing, before JMX generation begins.

#### Scenario: Reject zero write throughput
- **WHEN** a `WriteConfig` entry has `throughput=0`
- **THEN** the config parser SHALL raise a validation error referencing `throughput > 0`

#### Scenario: Reject negative query throughput
- **WHEN** a `QueryConfig` entry has `throughput=-1`
- **THEN** the config parser SHALL raise a validation error referencing `throughput > 0`

#### Scenario: Reject zero query throughput
- **WHEN** a `QueryConfig` entry has `throughput=0`
- **THEN** the config parser SHALL raise a validation error referencing `throughput > 0`

### Requirement: Multi-end throughput is the caller's responsibility
The system SHALL NOT perform multi-end throughput coordination. Each generated JMX is a single-end test plan that runs against a single KaiwuDB instance; the orchestration pipeline that runs multiple JMeter instances (one per KaiwuDB end) is responsible for dividing device numbers and (if applicable) per-end throughput ratios.

#### Scenario: Single JMX targets a single end
- **WHEN** the generator produces a JMX
- **THEN** there SHALL be no per-end throughput multipliers or splits inside the JMX itself
- **THEN** device-number allocation for the multi-end case is handled by the caller (pipeline that invokes JMeter), per the existing design decision on multi-end device-number roles

#### Scenario: No multi-end coordination logic
- **WHEN** reviewing the implementation
- **THEN** the `throughput_control` module SHALL NOT contain code that reads from multi-end config or splits throughput across ends

### Requirement: Live in the `src/throughput_control/` module
The system SHALL implement throughput-control as a standalone module under `src/throughput_control/` and consume it from `jmx_skeleton_generator` (replacing inline `constant_throughput_timer_element(...)` calls in `write_groups.py` / `query_groups.py`).

#### Scenario: Module layout
- **WHEN** the implementation is reviewed
- **THEN** there SHALL be a `src/throughput_control/__init__.py`
- **THEN** there SHALL be a `src/throughput_control/throughput_timer_generator.py`
- **THEN** `jmx_skeleton_generator/generators/write_groups.py` SHALL call `throughput_control` instead of building the timer inline

#### Scenario: Backward-compatible constant name exposure
- **WHEN** the module is consumed
- **THEN** it SHALL export `ThroughputTimerGenerator` plus `DEFAULT_WRITE_THROUGHPUT = 120.0` for the UDV default

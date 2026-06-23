## ADDED Requirements

### Requirement: Generate ConstantThroughputTimer for write thread groups
The system SHALL generate a ConstantThroughputTimer for each write thread group to control write throughput.

#### Scenario: Generate timer for write thread group
- **WHEN** generating a write thread group with `throughput=60`
- **THEN** the system SHALL generate a `ConstantThroughputTimer` element
- **THEN** the `throughput` property SHALL be `${write_throughput}`
- **THEN** the `calcMode` property SHALL be `0` (This thread only)
- **THEN** each thread SHALL independently target `60` samples per minute

### Requirement: Generate ConstantThroughputTimer for query thread groups
The system SHALL generate a ConstantThroughputTimer for each query thread group to control query throughput.

#### Scenario: Generate timer for query thread group
- **WHEN** generating a query thread group with `throughput=4`
- **THEN** the system SHALL generate a `ConstantThroughputTimer` element
- **THEN** the `throughput` property SHALL be `${query_throughput}`
- **THEN** the `calcMode` property SHALL be `0` (This thread only)
- **THEN** each thread SHALL independently target `4` samples per minute

### Requirement: Use calcMode 0 for per-thread targeting
The system SHALL set the `calcMode` property to `0` for ConstantThroughputTimer.

#### Scenario: Set calcMode in timer
- **WHEN** generating a ConstantThroughputTimer
- **THEN** the system SHALL set `<intProp name="calcMode">0</intProp>`
- **THEN** each thread SHALL independently target the specified throughput value

### Requirement: Support JMeter variable references
The system SHALL support JMeter variable references for throughput values.

#### Scenario: Use write_throughput variable
- **WHEN** a write thread group has `throughput=60`
- **THEN** the system SHALL use `${write_throughput}` in the timer expression
- **THEN** the variable SHALL be defined in `User Defined Variables`

#### Scenario: Use query_throughput variable
- **WHEN** a query thread group has `throughput=4`
- **THEN** the system SHALL use `${query_throughput}` in the timer expression
- **THEN** the variable SHALL be defined in `User Defined Variables`

### Requirement: Handle low throughput for queries
The system SHALL handle queries with very low throughput values correctly.

#### Scenario: Use exact throughput value
- **WHEN** a query has `throughput=0.016666667` (1 per minute)
- **THEN** the system SHALL use the exact value from config
- **THEN** the timer SHALL correctly target 1 sample per minute per thread
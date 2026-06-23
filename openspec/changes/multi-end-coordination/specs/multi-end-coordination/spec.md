## ADDED Requirements

### Requirement: Calculate device number range per table
The system SHALL calculate the device number range for each table independently.

#### Scenario: Calculate device range for single table
- **WHEN** a table has `num_threads=20`, `device_per_thread=10`, and `device_start=1`
- **THEN** the table's device range SHALL be `[1, 200]` (20 threads × 10 devices)
- **THEN** each thread SHALL be assigned a range of 10 consecutive device numbers

#### Scenario: Calculate local device start for thread
- **WHEN** thread index is 3, `device_per_thread=10`, and `device_start=1`
- **THEN** the local device start SHALL be `1 + 3 * 10 = 31`
- **THEN** the thread's device range SHALL be `[31, 40]`

### Requirement: Generate device number calculation script
The system SHALL generate a script for calculating device numbers in each write thread.

#### Scenario: Generate Groovy script
- **WHEN** generating JSR223PreProcessor for write thread group
- **THEN** the system SHALL include code to calculate `local_device_start`
- **THEN** the calculation SHALL be `device_start + ctx.getThreadNum() * device_per_thread`

### Requirement: Support multi-end coordination
The system SHALL support using multiple JMeter instances to scale test pressure.

#### Scenario: Use same test plan across instances
- **WHEN** using multiple JMeter instances
- **THEN** each instance SHALL use the same test plan (including throughput configuration)
- **THEN** instances SHALL differ only in the `device_start` parameter

#### Scenario: Calculate next instance's device_start
- **WHEN** current instance is processing table `t_cnc` with `num_threads=20` and `device_per_thread=10`
- **THEN** the next instance's device_start for this table SHALL be `current_device_start + 20 * 10`
- **THEN** device ranges SHALL not overlap for the same table across instances

### Requirement: Allow device range overlap across tables
The system SHALL allow device number ranges to overlap between different tables.

#### Scenario: Overlapping device ranges
- **WHEN** table `t_cnc` uses device range `[1, 200]` and table `t_motor` uses `[1, 100]`
- **THEN** the system SHALL allow the overlapping ranges
- **THEN** data for different tables SHALL be independent

### Requirement: Calculate device_start for next instance
The system SHALL provide the `device_start` value for the next JMeter instance.

#### Scenario: Output next device_start
- **WHEN** generating the test plan
- **THEN** the system SHALL output the `device_start` value for the next instance
- **THEN** the calculation SHALL be `max(device_start + num_threads * device_per_thread)` across all tables

### Requirement: Replace first Primary Tag with device identifier
The system SHALL replace the first Primary Tag placeholder with a device identifier.

#### Scenario: Generate device identifier
- **WHEN** a row's first Primary Tag placeholder is being replaced
- **THEN** the device identifier SHALL be `device_{local_device_start + (row_index % device_per_thread)}`
- **THEN** the identifier SHALL follow the pattern `device_{number}`
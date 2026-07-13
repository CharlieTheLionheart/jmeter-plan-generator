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

### Requirement: Single-source device number calculation across write modes
The system SHALL emit device-number calculation Groovy code through one shared helper so both ``batch_prepared`` (JSR223PreProcessor on the JSR223Sampler branch) and ``single_prepared`` (JSR223PreProcessor with single-row Groovy) reuse the same formula and arithmetic without copy/paste drift.

#### Scenario: Batch_prepared delegates to the helper
- **WHEN** ``BATCH_PREPARED_PREPROCESSOR_SCRIPT`` is rendered
- **THEN** its body SHALL call a shared Groovy function (e.g. ``calculateLocalDeviceStart(deviceStart, threadNum, devicePerThread)``) for ``localDeviceStart``
- **THEN** the helper SHALL be provided by ``utils.preprocessor_helpers.all_groovy_decls()``

#### Scenario: Single_prepared delegates to the same helper
- **WHEN** ``SinglePreparedStatementStrategy.get_preprocessor_code`` is rendered
- **THEN** its body SHALL reference the SAME shared helper rather than redefining ``device_start + threadNum * devicePerThread`` inline
- **THEN** the helper name SHALL match between the two strategies (single source of truth)

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

### Requirement: Expose device_start via JMeter property (not literal UDV value)
The system SHALL emit the ``device_start`` User Defined Variable value as the JMeter function reference ``${__P(device_start,1)}`` so that operators can override the starting device number per JMeter instance via the ``-Jdevice_start=N`` command-line property, without editing the JMX file. ``device_per_thread`` follows the same pattern (``${__P(device_per_thread,1)}``).

#### Scenario: UDV device_start references JMeter property
- **WHEN** the test plan is rendered
- **THEN** the UDV ``device_start`` field SHALL be the literal string ``"${__P(device_start,1)}"`` (NOT a numeric literal such as ``"1"``)
- **THEN** the UDV ``device_per_thread`` field SHALL be the literal string ``"${__P(device_per_thread,1)}"``

#### Scenario: JMeter -J property overrides the UDV default
- **WHEN** ``jmeter -Jdevice_start=1001 -n -t plan.jmx`` is invoked
- **THEN** the runtime value of ``device_start`` in every thread group SHALL be ``1001`` (not ``1``)
- **THEN** the ``write_thread_groups`` Groovy PreProcessor ``vars.get("device_start")`` SHALL observe the override

#### Scenario: Without -J override the documented default applies
- **WHEN** JMeter is started without ``-Jdevice_start``
- **THEN** the runtime value of ``device_start`` SHALL be ``1`` (the default in ``${__P(...)}``)

### Requirement: Multi-end orchestration is the caller's responsibility
The system SHALL NOT implement multi-end orchestration itself. Each generated JMX is a single-end test plan; the orchestration pipeline that runs multiple JMeter instances (one per KaiwuDB end) is responsible for:
- computing the ``device_start`` to pass to each instance,
- launching each instance with ``-Jdevice_start=<value>``,
- capturing any "next instance device_start" the operator may want.

The generator emits no Beanshell Listener, no JSR223 Sampler, no JMeter log statement, and no auxiliary output file whose purpose is to communicate device_start to the orchestration layer.

#### Scenario: Generated JMX has no multi-end output
- **WHEN** rendering a JMX end-to-end
- **THEN** there SHALL be NO ``<BeanShellSampler>``, ``<JSR223Sampler>``, ``<SampleLog>``, or extra file emitter whose purpose is "tell the pipeline which device_start to use next"
- **THEN** the only device_start path into the JMX SHALL be the UDV field ``${__P(device_start,1)}``

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
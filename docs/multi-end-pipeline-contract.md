# Multi-end Pipeline Contract

The JMX test plan generator ships a single-end `JMX` file. To run multiple
JMeter instances against the same plan against multiple KaiwuDB ends, the
orchestration **pipeline** (a `bash`/`python` script outside this project)
is responsible for splitting device-number ranges and launching each
instance with the right `-J` overrides.

This document captures the runtime contract between the generated JMX and
the orchestration pipeline.

> **Out of scope**: anything inside `src/jmx_skeleton_generator/` that *runs*
> during generation. This is a runtime instruction page for the operator.

---

## 1. Launching one JMeter instance against one KaiwuDB end

```bash
jmeter -n -t plan.jmx \
    -Jdevice_start=1 \
    -Jdevice_per_thread=10 \
    -Jdb_url=jdbc:kaiwudb://<host>/<db>
```

The generator renders the following fields as `${__P(name,default)}` JMeter
property references so they pick up `-J` overrides:

| UDV field | Default | Override via |
| --- | --- | --- |
| `device_start` | `1` (from `${__P(device_start,1)}`) | `-Jdevice_start=N` |
| `device_per_thread` | `1` (from `${__P(device_per_thread,1)}`) | `-Jdevice_per_thread=N` |

When `-J` is omitted, JMeter resolves `${__P(name,default)}` to the
default value (1 for both).

The following fields are still baked-in literals at generation time and
must be edited by hand if you want to override them outside the JMX
file: `db_url`, `db_username`, `db_password`, `conn_pool_size`,
`test_duration`, `write_throughput`. (`write_throughput` is rendered as
the literal `"120"`; -J override would not propagate.)

## 2. Multi-end: computing each instance's `device_start`

Across `K` JMeter instances hitting the same plan against `K` KaiwuDB
ends, the operator computes each instance's starting device number as:

```
device_start_inst_n = device_start_inst_1 + (n - 1) * num_threads * device_per_thread
```

The **same** `device_per_thread` and **same** `num_threads` apply to
every instance — only `device_start` advances.

Example with `num_threads=20`, `device_per_thread=10`:

| Instance | `-Jdevice_start=` |
| --- | --- |
| 1 | 1 |
| 2 | 201 |
| 3 | 401 |
| ... | ... |

Each table in the JMX has its own device range; in this version all
tables' ranges shift together (i.e. ranges from different tables may
overlap by design).

## 3. Boundary checks

The generator already enforces:
- `device_per_thread > 0` (config field `ge=1` + the
  `calculateLocalDeviceStart` helper rejects `<= 0` at JMeter runtime).
- `device_start >= 0` (config field `ge=0`).
- `throughput > 0` (config field `gt=0`).

If the pipeline launches the same instance twice with conflicting
`-Jdevice_start` (e.g. two pipelines racing for the same KaiwuDB),
the user-visible result is **data corruption in seed files** — two
threads will write to the same `device_N` row. This is the caller's
responsibility to prevent (e.g. via a leader-election or single-run
lock).

## 4. What the generator does NOT emit

The JMX contains no:
- `BeanShellSampler` / `JSR223Sampler` whose purpose is "tell the
  pipeline the next `device_start`".
- `SampleLog` listener writing the next-instance device_start to JMeter
  log.
- Output file emitter for orchestration metadata.

The orchestration pipeline does not consume any JMeter output to decide
the next instance — it computes the next `device_start` purely from
the YAML config + the instance index it launched.

## 5. Schema

```text
┌──────────────────────────────────────────────┐
│ pipeline                                    │
│   bash/python (not in this repo)            │
│   • loops K=2..N                            │
│   • computes device_start_inst_n            │
│   • launches: jmeter -n -t plan.jmx          │
│             -Jdevice_start=N                 │
└────────────┬─────────────────────────────────┘
             │ orchestrating only
             ▼
┌──────────────────────────────────────────────┐
│ JMeter instance n                           │
│   reads UDV ${__P(device_start,N)}           │
│   computes localDeviceStart in threadGroup   │
│   writes data with deviceId =               │
│       device_{localStart + (i % ...)}       │
└──────────────────────────────────────────────┘
```

## 6. Pipeline self-check template (Python)

```python
NUM_THREADS = 20
DEVICE_PER_THREAD = 10

for n in range(1, K + 1):
    device_start = 1 + (n - 1) * NUM_THREADS * DEVICE_PER_THREAD
    launch_jmeter(
        jmx_path="plan.jmx",
        overrides={"-Jdevice_start": device_start,
                   "-Jdevice_per_thread": DEVICE_PER_THREAD},
    )
```

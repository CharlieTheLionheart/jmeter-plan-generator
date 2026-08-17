# Tasks: col-tag-bind-per-group-subsets

> **Plan 索引**：本 change 是对 `openspec/changes/col-tag-bind-write/` 的语义修正（前 DCR 落地的是"每组共享前 N 列"简化版）。设计目标对照 `docs/superpowers/specs/2026-08-05-col-tag-bind-write-design.md` §1 Context（"设备 ↔ 列子集"语义）。
> **状态**：已落地 D-18 (offset) → D-19 (random) → D-21 (per-deviceCode key, 无 hash) commit `fcaef6f`。本 change 跟踪最终方案 D-21 落地全貌。

## §1. 落地全貌 — D-21 commit `fcaef6f`

- [x] 1.1 SetupTG row dict 二级 key：deviceCode (String) — 不再用 group_id (int)
- [x] 1.2 col_names offset：SetupTG 循环 index `t` (0..numThreads-1) — 不解析 deviceCode
- [x] 1.3 Write TG prep：`bindGroups.get(deviceCode) as Map` — 不用 hashCode/mod
- [x] 1.4 Write TG ThreadGroup `num_threads = WriteConfig.num_threads` — 修原 commit 5/6 硬编码 1
- [x] 1.5 spec.md §4 修订：value SHALL map deviceCode（不再 group_id）
- [x] 1.6 spec.md §4.5 删除 many-to-one mapping 段
- [x] 1.7 测试更新：6 个旧 case 不再 assert hashCode/mod-numThreads/group_id

## §2. 反退化 §8.8 升级 — DB 验证

- [x] 2.1 smoke 实测：device_1 + device_3 列子集 100% 互补（互不重叠）
- [x] 2.2 pytest 746 passed (739 + 6 D-9 + 1 D-21)，0 regress

## 全局验收

- [x] pytest 746/746 pass
- [x] smoke iot_monitor.meters：device_1 + device_3 列子集互补（互不重叠）
- [x] design §4.3 简化说明已更新（标注 [已修订 — 见 D-21]）
- [x] col-tag-bind-write/spec.md §4 已重写为 deviceCode key
- [x] todolist.md D-21 已 commit (`fcaef6f`)

## 后续 follow-up（独立 DCR，不在本 change）

- D-15：t_full full-row path escapeLineValue Groovy regex `PatternSyntaxException`
  （rest-schemaless §1-§5 范围，与 col-tag-bind-write 无关）
- D-17：JDBC bind path smoke（mode=batch_prepared + col_tag_bind_mode=true，未跑过真集群）

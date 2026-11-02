"""Phase B smoke 断言(write-missing-data)—— 落成正式 pytest 用例。

这些用例需要**真实 KaiwuDB 容器** + JMeter,默认**跳过**;opt-in 方式::

    KWJDB_SVT_SMOKE=1 python -m pytest tests/kwjdbc_svt/test_missing_smoke.py -v

断言口径见 ``openspec/changes/archive/2026-10-30-write-missing-data/tasks.md`` §9。

**为什么落成 pytest**:smoke 的断言口径(期望的落库形态 / 行数公式 / 失败模式)
原先只存在于临时驱动脚本里,重启即丢;落成用例后,口径变更会随代码一起被 review。

**判定口径说明**

- 行数期望 = ``组数 × 每设备批次数 × (D×B − M×N)``:
  一轮 = ``device_per_thread(D)`` 个设备 × ``batch_lines(B)`` 个时间戳;
  缺失取**交集**(设备尾部 M 个 ∩ ts 尾部 N 个)→ 丢弃 ``M×N`` 格。
- 每设备 distinct ts 数(归一到"每批次"口径)= ``{B, B−N}``:
  头部设备写满 B 个,尾部设备少 N 个 —— 这是缺失语义的核心观测。
- 满值设备数 : 截断设备数 == ``(D−M) : M`` —— 证明设备维的尾部截断。
- **不**断言"每个 ts 的设备数":多线程首批的 ``baseTime`` 可能落在同一毫秒,
  两个批次的 ts 值相撞 → 该 ts 的设备数翻倍,断言会随机翻车;
  等价事实已由"每设备 ts 覆盖数"覆盖。
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from kwjdbc_svt.main import EXIT_OK, main as cli_main


FIXTURE_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]

_SMOKE_ENV = "KWJDB_SVT_SMOKE"
_CONTAINER = os.environ.get("KWJDB_SVT_SMOKE_CONTAINER", "kaiwudb-smoke")
_CERTS_DIR = os.environ.get("KWJDB_SVT_SMOKE_CERTS_DIR", "/kaiwudb/certs")
_WORK = Path(os.environ.get("KWJDB_SVT_SMOKE_WORKDIR", "/tmp/kwjdbc-svt-smoke"))

pytestmark = pytest.mark.skipif(
    os.environ.get(_SMOKE_ENV) != "1",
    reason=f"需要真实 KaiwuDB 容器;opt-in: {_SMOKE_ENV}=1",
)


# ---------------------------------------------------------------------------
# 用例表
# ---------------------------------------------------------------------------
# kind:
#   shape      —— 6 条写入路径的缺失形态
#   prob       —— 概率触发(统计口径)
#   full_round —— 缺整轮(ts_count == batch_lines)
#   empty_pool —— 空种子池失败路径
#
# 字段:B=batch_lines, D=device_per_thread, M=device_count, N=ts_count,
#      threads=写线程数, rest=是否走 REST(TLS)通道。

_CASES: List[Dict[str, Any]] = [
    dict(tag="direct", kind="shape",
         cfg="test_cfg_missing_direct.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=1, N=2, threads=1, rest=False),
    dict(tag="direct_bind", kind="shape",
         cfg="test_cfg_missing_direct_bind.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=1, N=2, threads=1, rest=False),
    dict(tag="prepare", kind="shape",
         cfg="test_cfg_missing_prepare.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=1, N=2, threads=4, rest=False),
    dict(tag="prepare_bind", kind="shape",
         cfg="test_cfg_missing_prepare_bind.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=1, N=2, threads=4, rest=False),
    dict(tag="schemaless", kind="shape",
         cfg="test_cfg_missing_schemaless.yaml", model="test_model_schemaless.yaml",
         table="iot_monitor.meters", ts="k_timestamp", dev="ptag_varchar_1",
         B=2, D=2, M=1, N=1, threads=1, rest=True),
    dict(tag="schemaless_bind", kind="shape",
         cfg="test_cfg_missing_schemaless_bind.yaml", model="test_model_schemaless.yaml",
         table="iot_monitor.meters", ts="k_timestamp", dev="ptag_varchar_1",
         B=2, D=2, M=1, N=1, threads=1, rest=True),
    dict(tag="prob", kind="prob",
         cfg="test_cfg_missing_prob.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=1, N=2, threads=8, rest=False),
    dict(tag="full_round", kind="full_round",
         cfg="test_cfg_missing_full_round.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=0, N=5, threads=4, rest=False),
    dict(tag="full_round_direct", kind="full_round",
         cfg="test_cfg_missing_full_round_direct.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=0, N=5, threads=1, rest=False),
    dict(tag="full_round_schemaless", kind="full_round",
         cfg="test_cfg_missing_full_round_schemaless.yaml", model="test_model_schemaless.yaml",
         table="iot_monitor.meters", ts="k_timestamp", dev="ptag_varchar_1",
         B=2, D=2, M=0, N=2, threads=1, rest=True),
    dict(tag="empty_pool", kind="empty_pool",
         cfg="test_cfg_missing_prepare.yaml", model="test_model.yaml",
         table="iot_monitor.t_cnc", ts="ts", dev="ptag_varchar_1",
         B=5, D=2, M=1, N=2, threads=4, rest=False),
]

_CASE_IDS = [c["tag"] for c in _CASES]


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

def _sql(query: str) -> str:
    """在 KaiwuDB 容器里执行一条 SQL,返回原文(去掉尾部空行)。"""
    proc = subprocess.run(
        ["docker", "exec", _CONTAINER, "/kaiwudb/bin/kwbase", "sql",
         f"--certs-dir={_CERTS_DIR}", "-e", query],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"SQL 执行失败: {query}\n{proc.stdout}\n{proc.stderr}")
    return "\n".join(proc.stdout.splitlines())


def _scalar(query: str) -> int:
    """执行一条单列聚合 SQL,返回其整数值。"""
    lines = [l for l in _sql(query).splitlines() if l.strip()]
    assert lines, f"SQL 无输出: {query}"
    return int(lines[-1].split()[0])


def _distribution(query: str) -> Dict[int, int]:
    """解析 ``值<TAB>计数`` 两列输出,返回 ``{值: 计数}``(跳过表头)。"""
    out: Dict[int, int] = {}
    for line in _sql(query).splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            out[int(parts[0])] = int(parts[1])
    return out


def _generate_jmx(case: Dict[str, Any], out_dir: Path) -> Path:
    """生成测试计划;返回 .jmx 路径。"""
    rc = cli_main([
        str(FIXTURE_DIR / case["model"]),
        str(FIXTURE_DIR / case["cfg"]),
        "-o", str(out_dir),
    ])
    assert rc == EXIT_OK, f"JMX 生成失败: {case['cfg']} (rc={rc})"
    jmx = out_dir / "test_plan.jmx"
    assert jmx.is_file(), f"未产出 test_plan.jmx: {jmx}"
    return jmx


def _run_jmeter(case: Dict[str, Any], jmx: Path, out_dir: Path) -> Dict[str, Any]:
    """跑一次 jmeter -n;返回 JTL 解析结果与日志路径。"""
    jmeter = shutil.which("jmeter")
    assert jmeter, "找不到 jmeter 可执行文件"
    jtl = out_dir / f"{case['tag']}.jtl"
    log = out_dir / f"{case['tag']}.log"
    cmd = [
        jmeter, "-n", "-t", str(jmx),
        "-Jtest_duration=30",
        "-Jdb_url=jdbc:kaiwudb://127.0.0.1:26257/defaultdb",
        "-Jdb_username=root",
        f"-Jdb_password={os.environ.get('KWJDB_SVT_SMOKE_DB_PASSWORD', 'root123')}",
        "-l", str(jtl), "-j", str(log),
    ]
    if case["rest"]:
        cmd += [
            "-Jrest_api.hostname=127.0.0.1",
            "-Jrest_api.http_port=8081",
            f"-Jrest_api.ca_cert_path={FIXTURE_DIR / 'ca.crt'}",
        ]
    subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True, timeout=180)
    assert jtl.is_file(), f"未产出 JTL: {jtl}"

    rows: List[Dict[str, str]] = []
    with jtl.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    failed = [r for r in rows if r.get("success") != "true"]
    return {
        "rows": rows,
        "failed": failed,
        "write_samples": [r for r in rows if "Write" in (r.get("label") or "")],
        "log": log,
    }


def _prepare_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """准备一次 smoke:清表 → 生成 JMX → (可选)破坏种子 → 跑 jmeter。"""
    _sql(f"DROP TABLE IF EXISTS {case['table']}")
    out_dir = _WORK / case["tag"]
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    jmx = _generate_jmx(case, out_dir)
    if case["kind"] == "empty_pool":
        # 删掉行聚合 CSV(loader 的输入)→ loader 走"文件不存在"分支
        table = case["table"].split(".")[-1]
        for csv_file in out_dir.rglob("*.csv"):
            if csv_file.stem == table:
                csv_file.unlink()
    result = _run_jmeter(case, jmx, out_dir)
    result["out_dir"] = out_dir
    return result


def _log_exceptions(log: Path) -> List[str]:
    """从 jmeter.log 里摘出 JSR223 异常行(原文)。"""
    if not log.is_file():
        return []
    return [
        line.strip() for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
        if "Problem in JSR223 script" in line
    ]


# ---------------------------------------------------------------------------
# 断言
# ---------------------------------------------------------------------------

def _assert_shape(case: Dict[str, Any], result: Dict[str, Any]) -> None:
    """6 条写入路径的缺失形态:每设备 ts 覆盖数 + 行数 + 设备尾部比例。"""
    B, D, M, N = case["B"], case["D"], case["M"], case["N"]
    table, ts, dev = case["table"], case["ts"], case["dev"]

    assert not result["failed"], (
        f"{case['tag']}: sampler 报错 {[ (r['label'], r.get('responseCode')) for r in result['failed'] ]}"
    )
    assert not _log_exceptions(result["log"]), (
        f"{case['tag']}: preprocessor 异常 {_log_exceptions(result['log'])[:2]}"
    )

    total = _scalar(f"select count(*) from {table}")
    devices = _scalar(f"select count(distinct {dev}) from {table}")
    batches = len(result["write_samples"])
    assert batches > 0, f"{case['tag']}: 没有 Write sample"

    # 每设备经历的批次数 = 批次数 / 线程数(每线程一条设备区间)
    bpd = batches // case["threads"]
    assert bpd >= 1, f"{case['tag']}: 批次数 {batches} < 线程数 {case['threads']}"

    dist = _distribution(
        f"select ts_cov, count(*) from ("
        f"select {dev}, count(distinct {ts}) as ts_cov from {table} group by {dev}"
        f") x group by ts_cov order by 1"
    )
    # 归一到"每批次"口径
    normalized = {cov // bpd: n for cov, n in dist.items()}
    want = {B} | ({B - N} if M > 0 else set())
    assert set(normalized) == want, (
        f"{case['tag']}: 每设备 ts 覆盖数(归一)={sorted(normalized)} != 期望 {sorted(want)}"
    )

    # 行数 = 组数 × 每设备批次数 × (D×B − M×N)
    groups = devices // D
    expect_rows = groups * bpd * (D * B - M * N)
    assert total == expect_rows, (
        f"{case['tag']}: 落库 {total} 行 != 期望 {expect_rows}"
        f"(= {groups} 组 × {bpd} 批 × (D×B−M×N={D*B-M*N}))"
    )

    # 满值设备 : 截断设备 == (D−M) : M
    if M > 0:
        assert normalized[B] * M == normalized[B - N] * (D - M), (
            f"{case['tag']}: 满值设备 {normalized[B]} : 截断设备 {normalized[B-N]}"
            f" 不符 (D−M):M = {D-M}:{M}"
        )


def _assert_prob(case: Dict[str, Any], result: Dict[str, Any]) -> None:
    """概率触发:总行数在 [满量×0.5, 满量],且既有触发又有不触发的批次。"""
    B, D = case["B"], case["D"]
    table, ts, dev = case["table"], case["ts"], case["dev"]

    assert not result["failed"], f"{case['tag']}: sampler 报错"
    assert not _log_exceptions(result["log"]), f"{case['tag']}: preprocessor 异常"

    total = _scalar(f"select count(*) from {table}")
    batches = len(result["write_samples"])
    full = batches * D * B
    assert full * 0.5 <= total <= full, (
        f"{case['tag']}: 总行数 {total} 不在 [{full * 0.5}, {full}] 区间"
    )

    dist = _distribution(
        f"select ts_cov, count(*) from ("
        f"select {dev}, count(distinct {ts}) as ts_cov from {table} group by {dev}"
        f") x group by ts_cov order by 1"
    )
    assert any(cov < B for cov in dist), (
        f"{case['tag']}: 没有设备 ts 覆盖数 < {B} —— 概率未触发"
    )
    assert any(cov == B for cov in dist), (
        f"{case['tag']}: 没有设备 ts 覆盖数 == {B} —— 每批都缺了"
    )


def _assert_full_round(case: Dict[str, Any], result: Dict[str, Any]) -> None:
    """缺整轮:该批次零行写入,且不判为写入失败。"""
    assert not result["failed"], (
        f"{case['tag']}: 缺整轮却报错 "
        f"{[(r['label'], r.get('responseCode')) for r in result['failed']]}"
    )
    assert not _log_exceptions(result["log"]), f"{case['tag']}: preprocessor 异常"
    total = _scalar(f"select count(*) from {case['table']}")
    assert total == 0, f"{case['tag']}: 缺整轮却落了 {total} 行"


def _assert_empty_pool(case: Dict[str, Any], result: Dict[str, Any]) -> None:
    """空种子池:loader 与消费点都要报错 —— 失败模式如实暴露,不是"全绿但没写"。"""
    labels = {r.get("label") for r in result["failed"]}
    assert result["failed"], f"{case['tag']}: 种子池为空却全绿 —— 失败模式未暴露"
    assert any("SharedMemoryLoader" in (l or "") for l in labels), (
        f"{case['tag']}: SetupTG loader 未报错(报错 label: {sorted(labels)})"
    )
    assert any("Write" in (l or "") for l in labels), (
        f"{case['tag']}: Write TG 未二次报错(报错 label: {sorted(labels)})"
    )
    assert _scalar(f"select count(*) from {case['table']}") == 0, (
        f"{case['tag']}: 种子池为空却落了数据"
    )


_KIND_DISPATCH = {
    "shape": _assert_shape,
    "prob": _assert_prob,
    "full_round": _assert_full_round,
    "empty_pool": _assert_empty_pool,
}


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_missing_data_smoke(case: Dict[str, Any]) -> None:
    """write-missing-data 的 Phase B smoke 断言(逐用例)。"""
    result = _prepare_case(case)
    _KIND_DISPATCH[case["kind"]](case, result)

#!/usr/bin/env python3
"""生成 t_cnc 模板文件：k_timestamp 后删除原列，追加4096个数据列"""

# 10列 varchar(n)，n 取值范围 1~255
varchar_cols = [
    (1, 1), (2, 50), (3, 100), (4, 128), (5, 150),
    (6, 180), (7, 200), (8, 220), (9, 240), (10, 255)
]

# 10列 int4
int4_cols = list(range(11, 21))

# 其余都是 double: c21 ~ c4096
# 10 + 10 = 20，前20列已安排，剩下 4096 - 20 = 4076 列是 double
double_start = 21
double_count = 4096 - 20  # 4076

lines = ["k_timestamp timestamp false false _ [] true"]

# varchar 列
for idx, n in varchar_cols:
    lines.append(f"c{idx} varchar({n}) true false random_str [{n},true,true,NULL,0] false")

# int4 列
for idx in int4_cols:
    lines.append(f"c{idx} int4 true false random_int [0,2147483647,0] false")

# double 列
for i in range(double_count):
    idx = double_start + i
    lines.append(f"c{idx} double true false random_float [0,999999,2,0] false")

output_path = "gen.txt"
with open(output_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"生成完成，共 {len(lines)} 行，保存至 {output_path}")
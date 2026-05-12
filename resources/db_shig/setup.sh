#!/bin/bash
set -e

script_dir=$(dirname "$(realpath "$0")")
cmd="bash ${script_dir}/split_device.sh"

# 根据提供的参数数量扩展命令
if [[ $# -ge 1 ]]; then
    cmd+=" $*"
fi

eval "$cmd"

{ echo "CREATE TS DATABASE db_shig partition interval 1d;";\
echo "CREATE DATABASE db_shig_meta;";\
bash "${script_dir}"/../gen_sql.sh -t db_shig/t_cnc -m db_shig/t_cnc.meta; } >> "${script_dir}"/create.sql

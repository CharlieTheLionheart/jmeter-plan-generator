#!/bin/bash
set -e

script_dir=$(dirname "$(realpath "$0")")

{ echo "CREATE TS DATABASE db_pipec;";\
bash "${script_dir}"/../gen_sql.sh -t db_pipec/t_point -m db_pipec/t_point.meta; } >> "${script_dir}"/create.sql
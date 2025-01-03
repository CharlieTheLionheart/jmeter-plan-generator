#!/bin/bash
set -e

script_dir=$(dirname "$(realpath "$0")")
dup_cmd="bash ${script_dir}/dup_conf.sh -t pt100_dm_"

# 根据提供的参数数量扩展命令
if [[ $# -ge 1 ]]; then
    dup_cmd+=" $*"
fi

eval "$dup_cmd"

{ echo "CREATE TS DATABASE db_digital_ent;";\
bash "${script_dir}"/../gen_sql.sh -t db_digital_ent/stbl_event -m db_digital_ent/stbl_event.meta;\
bash "${script_dir}"/../gen_sql.sh -t db_digital_ent/stbl_raw -m db_digital_ent/stbl_raw.meta; } >> "${script_dir}"/create.sql

find "${script_dir}" -type f -name 'pt100_dm_*' | while read -r ptdm_file; do
  file_name="$(basename "${ptdm_file}")"
  if ! [[  "${ptdm_file}" =~ .meta$  ]] && [ "${file_name}" != "pt100_dm_" ]; then
    bash "${script_dir}"/../gen_sql.sh -t db_digital_ent/"${file_name}" -m db_digital_ent/pt100_dm_.meta >> "${script_dir}"/create.sql
  fi
done

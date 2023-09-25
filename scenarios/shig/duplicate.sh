#!/bin/env python3

base_dir=$(dirname -- "${BASH_SOURCE[0]}")
echo ${base_dir}

src_file=${1:-data_write.jmx}

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/plans/${src_file} \
  -d ${base_dir}/plans/data_write.jmx \
  --enable '\[Write\] 执行数据写入\(random\)' \
  --disable '\[Prepare\] 创建数据库,\[Prepare\] 创建模板表,\[Prepare\] 创建表,\[tearDown\] 删除数据库,\[tearDown\] 删除模板表,\[tearDown\] 删除子表,\[Prepare\] 配置'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/plans/${src_file} \
  -d ${base_dir}/plans/data_write.jmx \
  --disable '\[Write\] 执行数据写入\(random\),\[tearDown\] 删除数据库,\[tearDown\] 删除模板表,\[tearDown\] 删除子表' \
  --enable '\[Prepare\] 创建数据库,\[Prepare\] 创建模板表,\[Prepare\] 创建表,\[Prepare\] 配置'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/plans/${src_file} \
  -d ${base_dir}/plans/data_write.jmx \
  --enable '\[tearDown\] 删除数据库,\[tearDown\] 删除模板表,\[tearDown\] 删除子表' \
  --disable '\[Write\] 执行数据写入\(random\),\[Prepare\] 创建数据库,\[Prepare\] 创建模板表,\[Prepare\] 创建表,\[Prepare\] 配置'
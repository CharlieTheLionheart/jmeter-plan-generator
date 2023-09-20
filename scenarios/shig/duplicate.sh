#!/bin/env python3

base_dir=$(dirname -- "${BASH_SOURCE[0]}")
echo ${base_dir}

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/write_data_from_collector/data_write.jmx \
  -d ${base_dir}/meta_data_management/create_database.jmx \
  --disable '\[Write\] 执行数据写入\(random\)' --enable '\[Prepare\] 创建数据库'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/write_data_from_collector/data_write.jmx \
  -d ${base_dir}/meta_data_management/create_template_table.jmx \
  --disable '\[Write\] 执行数据写入\(random\)' --enable '\[Prepare\] 创建模板表'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/write_data_from_collector/data_write.jmx \
  -d ${base_dir}/meta_data_management/create_ts_tables.jmx \
  --disable '\[Write\] 执行数据写入\(random\)' --enable '\[Prepare\] 创建表'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/write_data_from_collector/data_write.jmx \
  -d ${base_dir}/meta_data_management/config.jmx \
  --disable '\[Write\] 执行数据写入\(random\)' --enable '\[Prepare\] 配置'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/write_data_from_collector/data_write.jmx \
  -d ${base_dir}/meta_data_management/drop_database.jmx \
  --disable '\[Write\] 执行数据写入\(random\)' --enable '\[tearDown\] 删除数据库'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/write_data_from_collector/data_write.jmx \
  -d ${base_dir}/meta_data_management/drop_template_table.jmx \
  --disable '\[Write\] 执行数据写入\(random\)' --enable '\[tearDown\] 删除模板表'

python3 ${base_dir}/../../dupjmx.py -s ${base_dir}/write_data_from_collector/data_write.jmx \
  -d ${base_dir}/meta_data_management/drop_ts_tables.jmx \
  --disable '\[Write\] 执行数据写入\(random\)' --enable '\[tearDown\] 删除子表'
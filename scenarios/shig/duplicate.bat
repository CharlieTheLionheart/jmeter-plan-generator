@echo off
chcp 65001

set base_dir=%~dp0

python %base_dir%\..\..\dupjmx.py -s %base_dir%\write_data_from_collector\data_write.jmx -d %base_dir%\meta_data_management\create_database.jmx --disable "\[Write\] 执行数据写入\(random\)" --enable "\[Prepare\] 创建数据库,\[Prepare\] 创建模板表,\[Prepare\] 创建表"

python %base_dir%\..\..\dupjmx.py -s %base_dir%\write_data_from_collector\data_write.jmx -d %base_dir%\meta_data_management\config.jmx --disable "\[Write\] 执行数据写入\(random\)" --enable "\[Prepare\] 配置"

python %base_dir%\..\..\dupjmx.py -s %base_dir%\write_data_from_collector\data_write.jmx -d %base_dir%\meta_data_management\drop_database.jmx --disable "\[Write\] 执行数据写入\(random\)" --enable "\[tearDown\] 删除数据库,\[tearDown\] 删除模板表,\[tearDown\] 删除子表"
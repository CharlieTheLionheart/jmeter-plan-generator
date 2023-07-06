# 采集器数据写入场景

## 文件列表
| 文件名 | 描述 |
|write_data_from_collector.jmx|省综逆变器写入场景的测试计划|

## 注意事项
1.write_data_from_collector.jmx的setup和teardown线程组为调试使用
2.minutes通过minutes调整jmx执行时间(单位：分钟)

ex.
jmeter -J db_url=jdbc:postgresql://127.0.0.1:26257/defaultdb \
  -J db_user=root -J db_passwd=123456 -J device_count=2 \
  -J csv_data_file=./data.csv -J ts_db=t_sgcc -J throughput=50000 \
  -J conn_pool_size=20 -n -t ./scenario_jdbc.jmx  -l ./result.csv
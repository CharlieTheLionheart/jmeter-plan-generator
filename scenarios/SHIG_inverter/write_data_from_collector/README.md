# 采集器数据写入场景

## 使用示例
ex.
jmeter -J db_url=jdbc:postgresql://127.0.0.1:26257/defaultdb \
  -J db_user=root -J db_passwd=123456 -J device_count=2 \
  -J csv_data_file=./data.csv -J ts_db=t_shig -J throughput=50000 \
  -J conn_pool_size=20 -n -t [name].jmx  -l [result].csv

1. -J: 传入配置变量
2. [name]: 编排文件名称
3. [result]: 输出报告
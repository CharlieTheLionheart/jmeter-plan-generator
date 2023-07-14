## 说明

### 1. 文件列表

1. data_write.jmx: 数据写入

### 2. 通用参数定义

> CSV数据

| 参数名称                    | 默认值                                         | 描述             |
|-------------------------|---------------------------------------------|----------------|
| db_url                  | jdbc:postgresql://127.0.0.1:26257/defaultdb | 	数据库连接jdbc url |
| db_user                 | root                                        | 	数据库连接用户       |
| db_passwd               | 123456                                      | 	数据库连接密码       |
| ts_db                   | db_shig                                     | 	创建时时序库名称      |
| write_throughput        | 50000                                       | 	写入吞吐量/min     |
| conn_pool_size          | 20                                          | 	线程池大小         |
| device_count_per_thread | 50                                          | 	每个线程模拟设备数量    |
| csv_sample_data         | test_plans/data.csv                         | 	插入样本数据文件      |
| data_ts_step            | 1000                                        | 	生成数据时间戳间隔ms   |

> 参数数据

| 参数名称        | 默认值        | 描述         |
|-------------|------------|------------|
| config_file | config.csv | 读入配置的CSV文件 |

### 3. 示例

```shell
    [/opt/path/bin]/jmeter -n -t data_write.jmx -l data_write-result.csv -J config_file=test_plans/config.csv
```

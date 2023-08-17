## 说明

### 1. 文件列表

1. setup_replication.jmx: 创建主备复制
2. create_database.jmx: 创建时序数据库 
3. create_template_table.jmx: 创建模板表
4. create_ts_tables.jmx: 创建时序表
5. pause_replication.jmx: 暂停主备复制
6. change_role.jmx: 切换主备角色 
7. resume_replication.jmx: 恢复主备复制 
8. drop_ts_tables.jmx: 删除时序表 
9. drop_template_table.jmx: 删除模板表 
10. drop_database.jmx: 删除时序数据库

### 2. 通用参数定义

> CSV 数据

| 参数名称                    | 默认值                                                                                                                                                                                                   | 描述                                               |
|-------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------|
| db_shig                 | 创建时时序库名称                                                                                                                                                                                              |
| write_throughput        | 50000                                                                                                                                                                                                 | 写入吞吐量/min                                        |
| device_count_per_thread | 50                                                                                                                                                                                                    | 每个线程模拟设备数量                                       |
| csv_sample_data         | test_plans/data.csv                                                                                                                                                                                   | 插入样本数据文件                                         |
| data_ts_step            | 1000                                                                                                                                                                                                  | 生成数据时间戳间隔 ms                                     |
| write_limit_per_thread  | 10000                                                                                                                                                                                                 | 每个线程执行的数据写入次数                                    |
| write_duration          | -1                                                                                                                                                                                                    | 写入持续时间,ISO8601 时间格式-1 表示不限制                      |
| write_stop_at           | -1                                                                                                                                                                                                    | 写入终止时间,时间格式参照"yyyy-MM-dd HH:mm:ss.SSS", -1 表示不限制 |
| device_no_start         | 1                                                                                                                                                                                                     | 起始设备编号,用于分布客户端创建                                 |
| backup_ip               | 127.0.0.1                                                                                                                                                                                             | 备节点ip                                            |
| bachup_port             | 26258                                                                                                                                                                                                 | 备节点port                                          |
| backup_url               | jdbc:postgresql://172.22.0.3:26258/defaultdb?mode=3&sslmode=verify-ca&sslcert=/home/liujin/certs/client.root.crt&sslkey=/home/liujin/certs/client.root.key.pk8&sslrootcert=/home/liujin/certs/ca.crt  | 组建主备集群时向主节点发送的备节点连接串                             |

> 参数数据

| 参数名称           | 默认值                                         | 描述             |
|----------------|---------------------------------------------|----------------|
| config_file    | config.csv                                  | 读入配置的 CSV 文件   |
| db_url         | jdbc:postgresql://127.0.0.1:26257/defaultdb | 数据库连接 jdbc url |
| db_user        | root                                        | 数据库连接用户        |
| conn_pool_size | 20                                          | 线程池大小          |

### 3. 示例

```shell
    [/opt/path/bin]/jmeter -n -t data_write.jmx -l data_write-result.csv \
      -J config_file=test_plans/config.csv ...
```

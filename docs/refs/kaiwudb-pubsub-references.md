以下是在一个真实部署的KaiwuDB数据库下执行发布本地库benchmark的cpu表并在sub_bench库的sub_cpu订阅此表的insert数据的示例操作流程
```
root@192.168.124.159:26257/defaultdb> CREATE TS DATABASE benchmark;
CREATE TS DATABASE

Time: 301.624439ms

root@192.168.124.159:26257/defaultdb> CREATE TABLE benchmark.cpu (k_timestamp TIMESTAMPTZ NOT NULL, usage_user INT8 NOT NULL, usage_system INT8 NOT NULL, usage_idle INT8 NOT NULL) TAGS (id INT8 NOT NULL, hostname VARCHAR NOT NULL, region VARCHAR NOT NULL, datacenter VARCHAR NOT NULL) PRIMARY TAGS (id);
CREATE TABLE

Time: 881.813223ms

root@192.168.124.159:26257/defaultdb> CREATE PUBLICATION cpu_filtered FOR TABLE benchmark.cpu (usage_user, usage_system, id);
CREATE PUBLICATION

Time: 1.276182668s

root@192.168.124.159:26257/defaultdb> create ts database sub_bench;
CREATE TS DATABASE

Time: 473.053467ms

root@192.168.124.159:26257/defaultdb> CREATE TABLE sub_bench.sub_cpu (k_timestamp TIMESTAMPTZ NOT NULL, usage_user INT8 NOT NULL, usage_system INT8 NOT NULL, usage_idle INT8 NOT NULL) TAGS (id
INT8 NOT NULL, hostname VARCHAR NOT NULL, region VARCHAR NOT NULL, datacenter VARCHAR NOT NULL) PRIMARY TAGS (id);

CREATE TABLE

Time: 509.158419ms

root@192.168.124.159:26257/defaultdb> CREATE SUBSCRIPTION sub_cpu CONNECTION 'postgresql://root1:Znbase%231234@192.168.124.159:26257/benchmark?ssl=disable' PUBLICATION cpu_filtered WITH OPTIONS
 (target='{"benchmark.public.cpu":"sub_bench.public.sub_cpu"}');
CREATE SUBSCRIPTION

Time: 17.072114226s
```
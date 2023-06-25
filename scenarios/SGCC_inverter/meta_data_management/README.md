# 历史数据查询场景

## 文件列表
| 文件名 | 描述 |
|:---|:---|
|create_device.jmx|创建device场景的测试计划|
|drop_device.jmx|销毁device场景的测试计划|

## 注意事项
1. create_device也包含drop_device的步骤，默认是屏蔽的，只是为了方便本地调试，drop_device同理
2. endpoint_info中的groupName需要与后续场景测试实际使用的endpointGroupName一致
#!/bin/bash
set -e

show_help() {
    echo "Split svt shig device from assigned from index and amount"
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  -h, --help         Show this help message and exit"
    echo "  -f, --from         Specify from idx of devices"
    echo "  -d, --digits       Do nothing, only adapt for param from other scenes"
    echo "  -n, --num          Specify amount of devices"
}

SHORT_OPTIONS=hf:n:d::
LONG_OPTIONS=help,from:,num:,digits::

PARSED=$(getopt --options $SHORT_OPTIONS --longoptions $LONG_OPTIONS --name "$0" -- "$@")
if [[ $? -ne 0 ]]; then
    echo "Error in command line arguments" >&2
    exit 1
fi

eval set -- "$PARSED"

from_idx=1
device_num=10
while true; do
    case "$1" in
        -d | --digits)
            shift 2
            ;;
        -f | --from)
            from_idx="$2"
            #echo "Option -f or --from specified with value: $from_idx"
            shift 2
            ;;
        -n | --num)
            device_num="$2"
            #echo "Option -n or --num specified with value: $device_num"
            shift 2
            ;;
        -h | --help)
            show_help
            exit 0
            ;;
        --)
            # 所有选项都已处理，剩余的参数是非选项参数
            break
            ;;
        *)
            # 不应该到达这里，因为 getopt 已经处理了所有有效的选项
            echo "Internal error in script" >&2
            exit 1
            ;;
    esac
done

end_idx=$(( from_idx + device_num - 1 ))

script_dir=$(dirname "$(realpath "$0")")
config_file_path="${script_dir}/single_battery"

# 在146和147匹配并删除157上映射docker目录时被本脚本追加进来，后续通过ansible copy带入的配置行
if [ -e "/root/user.properties" ]; then
  echo "$(sed '/^number/d' ${config_file_path})" > "${config_file_path}"
  # 重新追加本客户端的对应配置
  printf "number int false true serial_int [${from_idx},${end_idx}] true" >> "${config_file_path}"
fi

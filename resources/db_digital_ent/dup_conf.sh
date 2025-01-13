#!/bin/bash
set -e

show_help() {
    echo "Duplicate svt data config file from assigned template files"
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  -h, --help         Show this help message and exit"
    echo "  -t, --tmpl         Specify template file of svt config"
    echo "  -f, --from         Specify from idx of duplicated config files"
    echo "  -n, --num          Specify amount of duplicated config files"
    echo "  -d, --digits       Specify digits of name index for duplicated config files"
}

SHORT_OPTIONS=ht:f:n:d:
LONG_OPTIONS=help,tmpl:,from:,num:,digits:

PARSED=$(getopt --options $SHORT_OPTIONS --longoptions $LONG_OPTIONS --name "$0" -- "$@")
if [[ $? -ne 0 ]]; then
    echo "Error in command line arguments" >&2
    exit 1
fi

eval set -- "$PARSED"

tmpl_file=""
from_idx=1
conf_num=5
digits=2
while true; do
    case "$1" in
        -t | --tmpl)
            if [[ -z "$2" ]]; then
                echo "Error: Option -t or --tmpl requires an argument." >&2
                exit 1
            fi
            tmpl_file="$2"
            #echo "Option -t or --tmpl specified with value: $tmpl_file"
            shift 2
            ;;
        -f | --from)
            from_idx="$2"
            #echo "Option -f or --from specified with value: $from_idx"
            shift 2
            ;;
        -n | --num)
            conf_num="$2"
            #echo "Option -n or --num specified with value: $conf_num"
            shift 2
            ;;
        -d | --digits)
            digits="$2"
            #echo "Option -d or --digits specified with value: $digits"
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

if [ -z "${tmpl_file}" ];then
  echo "Error: Option -t or --tmpl required"
  exit 1
fi

prefix="${tmpl_file}"
suffix=""
if [[ "${tmpl_file}" == *.meta ]]; then
  suffix=".meta"
  prefix="${tmpl_file%.meta}"
fi

script_dir=$(dirname "$(realpath "$0")")
#echo "${script_dir}"

for (( i = from_idx; i <= from_idx + conf_num - 1; i++ )); do
    file_idx=${i}
    length=${#file_idx}

    #echo "$length"
    while [ "$length" -lt "$digits" ]; do
        file_idx="0${file_idx}"
        length=${#file_idx}
    done

    #echo "${prefix}${file_idx}${suffix}"
    dup_file_name="${prefix}${file_idx}${suffix}"
    cp "${script_dir}/${tmpl_file}" "${script_dir}/${dup_file_name}"
    sed -i "s#pt100_dm_01#${dup_file_name}#g" "${script_dir}/${dup_file_name}"
done

rm -fr "${script_dir}/${tmpl_file:-pt100_dm_}"
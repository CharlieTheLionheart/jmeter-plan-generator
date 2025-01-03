#!/bin/bash
set -ex

show_help() {
    echo "Generate svt create table sql file from assigned template files"
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  -h, --help         Show this help message and exit"
    echo "  -t, --tmpl         Specify template file of svt data config"
    echo "  -r, --rel          If gen relational table creation sql"
    echo "  -m, --meta         Specify meta file of ts table, optional"
}

SHORT_OPTIONS=ht:m:r
LONG_OPTIONS=help,tmpl:,meta:,rel

PARSED=$(getopt --options $SHORT_OPTIONS --longoptions $LONG_OPTIONS --name "$0" -- "$@")
if [[ $? -ne 0 ]]; then
    echo "Error in command line arguments" >&2
    exit 1
fi

eval set -- "$PARSED"

tmpl_file=""
meta_file=""
if_relational=""
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
        -m | --meta)
            meta_file="$2"
            #echo "Option -m or --meta specified with value: $meta_file"
            shift 2
            ;;
        -r | --rel)
            if_relational="true"
            shift 1
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

script_dir=$(dirname "$(realpath "$0")")

if [ ! -e "${script_dir}/${tmpl_file}" ]; then
    echo "Error: file ${script_dir}/${tmpl_file} does not exist"
    exit 1
fi

col_str="CREATE TABLE ${tmpl_file//\//\.} ("
tag_str=") ATTRIBUTES ("
while IFS=' ' read -r col_name col_type nullable is_tag rest; do
    if [ "$is_tag" = "true" ]; then
        tag_str="$tag_str$col_name $col_type"
        if [ "$nullable" = "false" ]; then
          tag_str="$tag_str NOT NULL"
        fi
        tag_str="$tag_str,"
    else
        col_str="$col_str$col_name $col_type"
        if [ "$nullable" = "false" ]; then
          col_str="$col_str NOT NULL"
        fi
        col_str="$col_str,"
    fi
done < "${script_dir}/${tmpl_file}"

last_line="$(tail -1 "${script_dir}/${tmpl_file}")"
col_name="$(echo "$last_line" | awk '{print $1}')"
col_type="$(echo "$last_line" | awk '{print $2}')"
nullable="$(echo "$last_line" | awk '{print $3}')"
is_tag="$(echo "$last_line" | awk '{print $4}')"

if [ "$is_tag" = "true" ]; then
    tag_str="$tag_str$col_name $col_type"
    if [ "$nullable" = "false" ]; then
      tag_str="$tag_str NOT NULL"
    fi
    tag_str="$tag_str,"
else
    col_str="$col_str$col_name $col_type"
    if [ "$nullable" = "false" ]; then
      col_str="$col_str NOT NULL"
    fi
    col_str="$col_str,"
fi

if [ "${if_relational}" = "true" ]; then
    sql_str="${col_str:0:-1}"
else
    sql_str="${col_str:0:-1}${tag_str:0:-1}"
fi

if [ -n "${meta_file}" ]; then
  sql_str="${sql_str}$(cat "${script_dir}/${meta_file}")"
fi

echo "$sql_str;"

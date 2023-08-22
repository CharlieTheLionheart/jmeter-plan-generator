#!/bin/env python3
# coding: utf-8

from argparse import ArgumentParser, Namespace, FileType
from os.path import basename
import re


def re_sub(src: str, testname: str, enable: bool) -> str:
    pattern = re.compile(
        rf'(<.*ThreadGroup.*testname="{testname}".*enabled=")(.+)(".*>)')
    return pattern.sub(rf'\g<1>{"true" if enable else "false"}\g<3>', src)


def main(args: Namespace) -> None:
    with open(args.dest, mode='w+', encoding='utf-8') as dest:
        with open(args.source, mode='r', encoding='utf-8') as source:
            source_content = source.read()
            disable_cases = args.disable.split(',')
            for d in disable_cases:
                source_content = re_sub(source_content, d, False)
            enable_cases = args.enable.split(',')
            for e in enable_cases:
                source_content = re_sub(source_content, e, True)
        dest.write(source_content)
        print(args.dest)


if __name__ == '__main__':
    parser = ArgumentParser(basename(__file__))

    parser.add_argument('-s', dest='source', required=True,
                        type=str, help='副本源文件路径')
    parser.add_argument('-d', dest='dest', required=True,
                        type=str, help='副本输出文件路径')
    parser.add_argument('--disable', dest='disable', type=str,
                        default='.*', help='关闭线程组名称支持正则表达式，默认值".*", 多个使用","连接')
    parser.add_argument('--enable', dest='enable', type=str,
                        help='打开线程组名称支持正则表达式,默认值为空, 多个使用","连接')

    main(parser.parse_args())

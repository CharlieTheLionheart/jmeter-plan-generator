import os
import pandas as pd

from argparse import ArgumentParser
from os.path import basename


def split_csv_files(input_dir, output_dir, rows_per_file=150):

    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 遍历输入目录下的所有文件
    for filename in os.listdir(input_dir):
        if filename.endswith('.csv'):
            # 读取CSV文件
            file_path = os.path.join(input_dir, filename)
            df = pd.read_csv(file_path)

            # 初始化批次号和输出文件名基础部分
            batch_no = 1
            base_output_filename = os.path.splitext(filename)[0]

            # 计算总批次数
            total_batches = (len(df) + rows_per_file - 1) // rows_per_file

            # 分割文件并保存批次
            for i in range(total_batches):
                start_row = i * rows_per_file
                end_row = min((i + 1) * rows_per_file, len(df))

                # 创建输出文件名
                output_filename = f"{base_output_filename}_{batch_no}.csv"
                output_file_path = os.path.join(output_dir, output_filename)

                # 保存当前批次到文件
                df[start_row:end_row].to_csv(output_file_path, index=False)

                # 更新批次号
                batch_no += 1

if __name__ == '__main__':

    parser = ArgumentParser(basename(__file__))
    parser.add_argument('-r', dest='rows_per_file', help='rows per file',
                        default=150, type=int)
    parser.add_argument('-i', dest='input_dir',
                        help='input directory to split csv file by amount',
                        default='./pipec_data_files', type=str)
    parser.add_argument('-o', dest='output_dir', help='output directory to save split csv files',
                        default='./pipec_data_files_splited', type=str)

    args = parser.parse_args()
    rows_per_file = args.rows_per_file
    input_dir = args.input_dir
    output_dir = args.output_dir

    split_csv_files(input_dir, output_dir, rows_per_file)

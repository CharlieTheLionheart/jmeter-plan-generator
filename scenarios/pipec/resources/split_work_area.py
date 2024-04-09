import csv
import errno
import os
import random

from argparse import ArgumentParser
from os.path import basename


class MeasurePoint:
    def __init__(self, point_sn, work_area_sn, sub_com_sn, station_sn, pipeline_sn, measure_type):
        self.measure_value = 0.0
        self.point_sn = point_sn
        self.work_area_sn = work_area_sn
        self.sub_com_sn = sub_com_sn
        self.station_sn = station_sn
        self.pipeline_sn = pipeline_sn
        self.measure_type = measure_type


# Split input csv file to dict of work_area with key of split_file_name, witch is the thread num of jmeter thread
def split_by_work_area(total_file: str, amount_per_work_area: int) -> dict:

    work_area_dict = {}
    with open(total_file, mode='r', newline='') as to_split_file:
        csv_reader = csv.DictReader(to_split_file)

        # use index as file name for jmeter thread to match with thread num
        split_file_name = 0
        # batch num in the same work_area_sn
        work_area_batch_num = 1
        # row num in he same work_area_sn
        work_area_row_num = 1
        # tmp work_area_sn to judge if the work_area_sn has changed
        work_area_tmp = ''
        # list to save measure_point objects
        measure_point_list = []

        for row in csv_reader:

            # set work_area_tmp to this work_area_sn if changed
            if  work_area_change(work_area_tmp, row['work_area_sn']):
                work_area_tmp = row['work_area_sn']
                '''
                Reset work_area_batch_num number and work_area_row_num if got next work_area, 
                and add split_file_name to the next
                '''
                work_area_batch_num = 1
                work_area_row_num = 1
                split_file_name += 1
                measure_point_list = []

            # get MeasurePoint obj from row
            measure_point = MeasurePoint(
                row['point_sn'].replace("\n", ""),
                row['work_area_sn'].replace("\n", ""),
                row['sub_com_sn'].replace("\n", ""),
                row['station_sn'].replace("\n", ""),
                row['pipeline_sn'].replace("\n", ""),
                row['measure_type']
            )

            # use next work_area_batch_num and reset measure_point_list if got next batch
            if work_area_row_num > work_area_batch_num * amount_per_work_area:
                work_area_batch_num += 1
                split_file_name += 1
                measure_point_list = []

            # append measure_point to measure_point_list
            measure_point_list.append(measure_point)
            # save measure_point_list to dict of work_area with key of ${split_file_name} format
            work_area_dict[str(split_file_name)] = measure_point_list
            work_area_row_num += 1

    return work_area_dict


def work_area_change(origin_work_area_sn: str, to_compare_work_area_sn: str) -> bool:
    return origin_work_area_sn != to_compare_work_area_sn


def write_output_files(work_area_dict: dict, output_path: str):
    current_path = os.getcwd()
    path_to_create = os.path.join(current_path, output_path)
    try:
        os.makedirs(path_to_create)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise  # 如果不是目录已存在的错误，则抛出异常

    fieldnames = [
            'measure_value',
            'point_sn',
            'work_area_sn',
            'sub_com_sn',
            'station_sn',
            'pipeline_sn',
            'measure_type'
        ]

    for work_area_key, work_area_objs in work_area_dict.items():
        out_file_path = os.path.join(path_to_create, work_area_key + '.csv')
        with open(out_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            # 创建一个csv writer对象
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for work_area in work_area_objs:
                setattr(work_area, 'measure_value', generate_point_value(getattr(work_area, 'measure_type')))
                row_dict = {
                    'measure_value': work_area.measure_value,
                    'point_sn': "'" + work_area.point_sn + "'",
                    'work_area_sn': "'" + work_area.work_area_sn + "'",
                    'sub_com_sn': "'" + work_area.sub_com_sn + "'",
                    'station_sn': "'" + work_area.station_sn + "'",
                    'pipeline_sn': "'" + work_area.pipeline_sn + "'",
                    'measure_type': work_area.measure_type
                }
                writer.writerow(row_dict)


def generate_point_value(measure_type: str) -> float:
    if measure_type_is_status(measure_type):
        return float(random.randint(1,6))
    return random.random() * 10


def measure_type_is_status(measure_type: str) -> bool:
    # 数据类型>10是状态量，否则是模拟量
    return int(measure_type) > CONST_DATAPOINT_IS_STATUS_FROM


if __name__ == '__main__':

    CONST_DATAPOINT_IS_STATUS_FROM: int = 10 # 类型大于10是状态量，否则是模拟量

    parser = ArgumentParser(basename(__file__))
    parser.add_argument('-a', dest='amount_of_point', help='amount of points to split',
                        default=300, type=int)
    parser.add_argument('-i', dest='input_file', help='input csv file to split', default='./point_sorted.csv', type=str)
    parser.add_argument('-o', dest='output_dir', help='output directory to save split csv files',
                        default='./pipec_data_files', type=str)

    args = parser.parse_args()
    amount_of_point = args.amount_of_point
    input_file = args.input_file
    output_dir = args.output_dir

    write_output_files(split_by_work_area(input_file, amount_of_point), output_dir)

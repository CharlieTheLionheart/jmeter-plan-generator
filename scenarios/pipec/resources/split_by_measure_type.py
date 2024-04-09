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
def split_by_measure_type(total_file: str) -> dict:

    work_area_dict = {}
    with open(total_file, mode='r', newline='') as to_split_file:
        csv_reader = csv.DictReader(to_split_file)

        # list to save measure_point objects bu type
        measure_list_0 = []
        measure_list_1 = []
        measure_list_2 = []
        measure_list_3 = []
        measure_list_4 = []
        measure_list_5 = []
        measure_list_6 = []
        measure_list_7 = []
        measure_list_8 = []
        measure_list_9 = []
        measure_list_10 = []
        measure_list_11 = []
        measure_list_12 = []
        measure_list_13 = []
        measure_list_14 = []
        measure_list_15 = []
        measure_list_16 = []
        measure_list_17 = []

        for row in csv_reader:

            point_sn = row['point_sn'].replace("\n", "")
            work_area_sn = row['work_area_sn'].replace("\n", "")
            sub_com_sn = row['sub_com_sn'].replace("\n", "")
            station_sn = row['station_sn'].replace("\n", "")
            pipeline_sn = row['pipeline_sn'].replace("\n", "")
            measure_type = row['measure_type'].replace(" ", "")

            # get MeasurePoint obj from row
            measure_point = MeasurePoint(
                point_sn,
                work_area_sn,
                sub_com_sn,
                station_sn,
                pipeline_sn,
                measure_type
            )

            if measure_type == "0":
                measure_list_0.append(measure_point)
            elif measure_type == "1":
                measure_list_1.append(measure_point)
            elif measure_type == "2":
                measure_list_2.append(measure_point)
            elif measure_type == "3":
                measure_list_3.append(measure_point)
            elif measure_type == "4":
                measure_list_4.append(measure_point)
            elif measure_type == "5":
                measure_list_5.append(measure_point)
            elif measure_type == "6":
                measure_list_6.append(measure_point)
            elif measure_type == "7":
                measure_list_7.append(measure_point)
            elif measure_type == "8":
                measure_list_8.append(measure_point)
            elif measure_type == "9":
                measure_list_9.append(measure_point)
            elif measure_type == "10":
                measure_list_10.append(measure_point)
            elif measure_type == "11":
                measure_list_11.append(measure_point)
            elif measure_type == "12":
                measure_list_12.append(measure_point)
            elif measure_type == "13":
                measure_list_13.append(measure_point)
            elif measure_type == "14":
                measure_list_14.append(measure_point)
            elif measure_type == "15":
                measure_list_15.append(measure_point)
            elif measure_type == "16":
                measure_list_16.append(measure_point)
            elif measure_type == "17":
                measure_list_17.append(measure_point)

            work_area_dict["0"] = measure_list_0
            work_area_dict["1"] = measure_list_1
            work_area_dict["2"] = measure_list_2
            work_area_dict["3"] = measure_list_3
            work_area_dict["4"] = measure_list_4
            work_area_dict["5"] = measure_list_5
            work_area_dict["6"] = measure_list_6
            work_area_dict["7"] = measure_list_7
            work_area_dict["8"] = measure_list_8
            work_area_dict["9"] = measure_list_9
            work_area_dict["10"] = measure_list_10
            work_area_dict["11"] = measure_list_11
            work_area_dict["12"] = measure_list_12
            work_area_dict["13"] = measure_list_13
            work_area_dict["14"] = measure_list_14
            work_area_dict["15"] = measure_list_15
            work_area_dict["16"] = measure_list_16
            work_area_dict["17"] = measure_list_17

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
    parser.add_argument('-i', dest='input_file', help='input csv file to split', default='./point_sorted.csv', type=str)
    parser.add_argument('-o', dest='output_dir', help='output directory to save split csv files',
                        default='./pipec_data_files', type=str)

    args = parser.parse_args()
    input_file = args.input_file
    output_dir = args.output_dir

    write_output_files(split_by_measure_type(input_file), output_dir)
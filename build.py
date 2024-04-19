#!/bin/env python3
# coding: utf-8

from os import path, makedirs
from shutil import copytree, rmtree
from xml.etree.cElementTree import parse as xmlparse
from copy import deepcopy


def process_pipec():
  dir_data = path.realpath(path.join(path.curdir, 'docker/data/pipec'))
  dir_plan = path.realpath(path.join(path.curdir, 'docker/plans/pipec'))
  if path.exists(dir_data):
    rmtree(dir_data)
  if path.exists(dir_plan):
    rmtree(dir_plan)
  # 复制数据
  copytree(path.realpath(path.join(path.curdir, 'scenarios/pipec/resources')), dir_data)
  # 直接复制测试计划
  copytree(path.realpath(path.join(path.curdir, 'scenarios/pipec/plans')), dir_plan)


def process_shig():
  dir_data = path.realpath(path.join(path.curdir, 'docker/data/shig'))
  dir_plan = path.realpath(path.join(path.curdir, 'docker/plans/shig'))
  if path.exists(dir_data):
    rmtree(dir_data)
  if path.exists(dir_plan):
    rmtree(dir_plan)
  makedirs(dir_plan)
  # 复制数据
  copytree(path.realpath(path.join(path.curdir, 'scenarios/shig/resources')), dir_data)
  # 拆分测试计划
  jmx = xmlparse(path.realpath(path.join(path.curdir, 'scenarios/shig/plans/plan.jmx')))
  # 禁用TD
  for element in jmx.findall(".//"):
    if "[TD]" in element.get("testname", ''):
      element.set("enabled", "false")
  # setup-1
  jmx_setup1 = deepcopy(jmx)
  for element in jmx_setup1.getroot().findall(".//ThreadGroup") + jmx_setup1.getroot().findall(".//PostThreadGroup"):
    if "[User]" in element.get("testname", ''):
      element.set("enabled", "true")
    else:
      element.set("enabled", "false")
  jmx_setup1.write(path.realpath(path.join(dir_plan, 'setup-1.jmx')))
  # setup-2
  jmx_setup2 = deepcopy(jmx)
  for element in jmx_setup2.getroot().findall(".//ThreadGroup") + jmx_setup1.getroot().findall(".//PostThreadGroup"):
    if "[Prepare]" in element.get("testname", ''):
      element.set("enabled", "true")
    else:
      element.set("enabled", "false")
  jmx_setup2.write(path.realpath(path.join(dir_plan, 'setup-2.jmx')))
  # write-1
  jmx_write1 = deepcopy(jmx)
  for element in jmx_write1.getroot().findall(".//ThreadGroup") + jmx_setup1.getroot().findall(".//PostThreadGroup"):
    if "[Write]" in element.get("testname", ''):
      element.set("enabled", "true")
    else:
      element.set("enabled", "false")
  jmx_write1.write(path.realpath(path.join(dir_plan, 'write-1.jmx')))
  # query-1
  jmx_query1 = deepcopy(jmx)
  for element in jmx_query1.getroot().findall(".//ThreadGroup") + jmx_setup1.getroot().findall(".//PostThreadGroup"):
    if "[Query]" in element.get("testname", ''):
      element.set("enabled", "true")
    else:
      element.set("enabled", "false")
  jmx_query1.write(path.realpath(path.join(dir_plan, 'query-1.jmx')))


if __name__ == '__main__':
  process_pipec()
  process_shig()

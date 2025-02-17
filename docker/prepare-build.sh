#!/bin/bash
set -e

mvn install --file=mvn/pom.xml --settings=mvn/settings.xml \
  dependency:copy-dependencies -DoutputDirectory=jars

scene_arr=("shig" "digital_ent" "pipec" "baoguang")
for scene in "${scene_arr[@]}";do
  mkdir -p ../scenarios/"${scene}"/resources/ data plans/"${scene}"
  cp -r ../resources/* data
  cp -f ../scenarios/"${scene}"/plans/plan.jmx plans/"${scene}"
done
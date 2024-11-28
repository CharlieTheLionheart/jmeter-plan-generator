#!/bin/bash
set -e

mvn install --file=mvn/pom.xml --settings=mvn/settings.xml \
  dependency:copy-dependencies -DoutputDirectory=jars

rm -fr line2-om-utils
git clone -b develop \
--filter=blob:none \
--no-checkout \
ssh://git@devops.inspur.com:30004/ISG__ZDP/line2-om-utils.git line2-om-utils

cd line2-om-utils

git sparse-checkout init --cone
git sparse-checkout set test-data-gen/
git checkout

cd test-data-gen
scene_arr=("shig" "digital_ent")
for scene in "${scene_arr[@]}";do
  python3 main.py -c "db_${scene}" -b ../../../resources
done

cd ../..

for scene in "${scene_arr[@]}";do
  mkdir -p ../scenarios/"${scene}"/resources/ data/"${scene}" plans/"${scene}"
  cp ../resources/db_"${scene}"/* ../scenarios/"${scene}"/resources/
  cp -f ../scenarios/"${scene}"/plans/plan.jmx plans/"${scene}"
  cp -f ../scenarios/"${scene}"/resources/* data/"${scene}"
done

mv ../scenarios/shig/resources/t_electmeter.csv ../scenarios/shig/resources/data.csv
mv ../scenarios/shig/resources/t_tighten.csv ../scenarios/shig/resources/tighten_data.csv
mv ../scenarios/shig/resources/t_cnc.csv ../scenarios/shig/resources/cnc_data.csv

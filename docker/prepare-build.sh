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
python3 main.py -c 'db_shig' -b ../../../resources
cd ../..

cp ../resources/db_shig/*.csv ../scenarios/shig/resources/
mv ../scenarios/shig/resources/t_electmeter.csv ../scenarios/shig/resources/data.csv
mv ../scenarios/shig/resources/t_tighten.csv ../scenarios/shig/resources/tighten_data.csv
mv ../scenarios/shig/resources/t_cnc.csv ../scenarios/shig/resources/cnc_data.csv

mkdir -p data/pipec data/shig plans/pipec plans/shig
cp -f ../scenarios/pipec/plans/plan.jmx plans/pipec
cp -f ../scenarios/pipec/resources/* data/pipec
cp -f ../scenarios/shig/plans/plan.jmx plans/shig
cp -f ../scenarios/shig/resources/* data/shig

#!/bin/bash
set -ex

echo "exec docker entry point"
if [ -e "/data/db_${TEST}/setup.sh" ];then
  cmd="bash /data/db_${TEST}/setup.sh"
  if [[ $# -ge 1 ]];then
    cmd+=" $*"
  fi
  eval "$cmd"
fi

/usr/local/lib/apache-jmeter-${JMETER_VER}/bin/jmeter -n \
  -o /root/result/report \
  -l /root/result/result.csv \
  -t /plans/${TEST}/plan.jmx \
  -i /root/log4j2.xml \
  -q /root/jmeter.properties \
  -q /root/user.properties \
  -J user.db.url="${DBURL}"
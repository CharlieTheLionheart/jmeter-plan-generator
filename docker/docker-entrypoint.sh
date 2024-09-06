#!/bin/bash
set -e

if [ -n "$1" ]; then
  exec "$@"
else
  /usr/local/lib/apache-jmeter-${JMETER_VER}/bin/jmeter -n \
    -o /root/result/report \
    -l /root/result/result.csv \
    -t /plans/${TEST}/plan.jmx \
    -i /root/log4j2.xml \
    -q /root/jmeter.properties \
    -q /root/user.properties \
    -J user.db.url="${DBURL}" \
    -J user.db.taos_url="${TAOSURL}"
fi
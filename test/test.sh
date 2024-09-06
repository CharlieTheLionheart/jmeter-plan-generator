#!/bin/bash
set -e

docker compose down -v
docker compose up -d
sleep 5

rm -fr ./result
docker run --rm -ti --net=host \
  -e TAOSURL='jdbc:TAOS://127.0.0.1:6030' \
  -e DBURL='jdbc:kaiwudb://127.0.0.1:26257/defaultdb?sslmode=disable&user=root' \
  -v ./result:/root/result \
  devops.inspur.com:80/isg/zdp/repo/local_repo/daily_svt/test_components/svt-web-app

read -p "press any key clean...(cancel with press Ctrl+C)"
docker compose down -v
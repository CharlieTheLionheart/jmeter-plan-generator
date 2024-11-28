#!/bin/bash
set -e

source ./prepare-build.sh

IMAGE_REPO=${IMAGE_REPO:-devops.inspur.com:80/isg/zdp/repo/local_repo/quality_team}
IMAGE_NAME=${IMAGE_NAME:-test_components/ubuntu-2004-svt-data-collector}
IMAGE_VER=${1:-20241128}

docker build --build-arg OPENJDK_VER=openjdk-21-jre-headless \
  --build-arg JMETER_VER=5.6.3 \
  --build-arg KWJDBC_VER=2.1.0 \
  -t "${IMAGE_REPO}/${IMAGE_NAME}:${IMAGE_VER}" .

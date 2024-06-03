FROM devops.inspur.com:80/isg/zdp/repo/local_repo/quality_team/test_components/ubuntu-2004-svt-data-collector:20240105
LABEL maintainer=liujinwei@inspur.com
USER root

COPY data /data
COPY plans /plans

COPY svt-jar-with-dependencies.jar /usr/local/lib/apache-jmeter-5.5/lib/ext/
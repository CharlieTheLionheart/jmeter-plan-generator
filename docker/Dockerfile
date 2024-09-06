FROM ubuntu:20.04
LABEL maintainer=liujinwei@inspur.com
USER root

ARG OPENJDK_VER
RUN apt update && apt install -yq curl ${OPENJDK_VER}
LABEL openjdk_ver=${OPENJDK_VER}

ARG JMETER_VER
RUN curl -o - -fsSL \
  https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VER}.tgz | \
  tar -C /usr/local/lib -zxf -
LABEL jmeter_ver=${JMETER_VER}
COPY log4j2.xml /usr/local/lib/apache-jmeter-${JMETER_VER}/bin
COPY jmeter.properties /usr/local/lib/apache-jmeter-${JMETER_VER}/bin

COPY mvn/jars /usr/local/lib/apache-jmeter-${JMETER_VER}/lib/ext
ARG KWJDBC_VER
LABEL kwjdbc_ver=${KWJDBC_VER}

COPY data /data
COPY plans /plans
COPY jmeter.properties log4j2.xml /root/

ENV JMETER_VER="${JMETER_VER}"
ENV DBURL=""
ENV TEST="shig"

VOLUME /root/result
WORKDIR /root/result

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN touch /root/user.properties && apt clean && rm -fr /tmp/*

ENTRYPOINT [ "/docker-entrypoint.sh" ]
#!/bin/bash

git clone -b develop ssh://git@devops.inspur.com:30004/ISG__ZDP/svt-data-generator.git
cd svt-data-generator
mvn package
mv target/svt-jar-with-dependencies.jar ../docker
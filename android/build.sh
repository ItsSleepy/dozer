#!/bin/bash
cd /home/sleepy/dozer/android
export ANDROID_SDK_ROOT=/home/sleepy/android-sdk
export JAVA_HOME=/home/sleepy/jdk-17
export PATH=$JAVA_HOME/bin:$PATH
export TMPDIR=/home/sleepy/dozer/android/.tmp
export JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/home/sleepy/dozer/android/.tmp
export DOZER_KS_PASS=$(grep ^DOZER_KS_PASS= /home/sleepy/dozer/.env | cut -d= -f2)
/home/sleepy/gradle-8.10.2/bin/gradle --no-daemon -q assembleRelease > build.log 2>&1
echo "EXIT $?" >> build.log

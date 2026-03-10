#!/bin/bash

sudo apt update
sudo apt install -y openjdk-21-jdk

# Set JAVA_HOME for the current user
echo "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64" >> ~/.bashrc
echo "export PATH=\$JAVA_HOME/bin:\$PATH" >> ~/.bashrc

# Reload shell config
source ~/.bashrc

java -version

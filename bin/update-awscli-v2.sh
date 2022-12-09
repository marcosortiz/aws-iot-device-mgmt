#!/bin/bash

cd /tmp/
wget -q https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
unzip -q awscli-exe-linux-x86_64.zip
sudo ./aws/install --update
rm -rf aws
rm -f awscli-exe-linux-x86_64.zip

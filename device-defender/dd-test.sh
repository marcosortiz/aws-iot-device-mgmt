#!/bin/bash

# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

#
# dd-test.sh
#
# test for AWS IoT Device Defender

THING_NAME="dd-test"
THING_GROUP_NAME="dd-unexpected-activity"

if [ ! -e $THING_NAME.certificate.pem -a ! -e $THING_NAME.private.key ]; then

    if ! aws iot describe-thing-group --thing-group-name $THING_GROUP_NAME > /dev/null 2>&1; then 
        echo "  create thing group \"$THING_GROUP_NAME\""
        aws iot create-thing-group --thing-group-name $THING_GROUP_NAME
    fi
    
    ~/bin/create-device.sh $THING_NAME
    
    echo "  add thing to group \"$THING_GROUP_NAME\""
    aws iot add-thing-to-thing-group --thing-group-name $THING_GROUP_NAME --thing-name $THING_NAME
fi

echo "starting thing \"$THING_NAME\"..."

sleep 2

~/virtual-sensor/virtual-sensor.py -e $IOT_ENDPOINT \
    -r ~/root.ca.bundle.pem -c dd-test.certificate.pem -k dd-test.private.key \
    -id $THING_NAME
    
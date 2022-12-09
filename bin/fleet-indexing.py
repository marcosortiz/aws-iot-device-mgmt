#!/usr/bin/env python3.7

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
# fleet-indexing.py
#
# Adds a reported temperature to device shadow matching the "devicename*"
"""
   Adds a reported temperature to
   device shadow matching the "devicename*"
"""

import argparse
import json
import os
import random
import time

import boto3

parser = argparse.ArgumentParser(
    description='Add shadow reported.reported.temperature to the things matching basename*'
)
parser.add_argument("-b", action="store", required=True, dest="thing_base_name",
                    help="Basename of the things to which the shadow document should be added.")

args = parser.parse_args()
thing_base_name = args.thing_base_name


IOT_ENDPOINT = os.environ['IOT_ENDPOINT']
building_names = ['Day_One', 'Doppler', 'Kumo']
ROOM_NUMBER = 100

def shadow_doc():
    """Generate a shadow
    document with a random temperature
    """

    temp = random.randint(15,30)
    return {
    "state": {
        "reported" : {
            "temperature" : temp
        }
    }
}


c_iot = boto3.client('iot')
c_iot_data = boto3.client('iot-data', endpoint_url='https://{}'.format(IOT_ENDPOINT))

query_string = "thingName:" + thing_base_name + "*"
print("query_string: {}".format(query_string))
response = c_iot.search_index(
#    indexName='string',
    queryString=query_string,
#    nextToken='string',
#    maxResults=123,
#    queryVersion='string'
)


print("response:\n{}".format(response))

for thing in response["things"]:
    thing_name = thing["thingName"]
    shadow_document = json.dumps(shadow_doc(), indent=4)
    print("updating shadow for thing name: {}".format(thing_name))
    print("shadow document: {}".format(shadow_document))
    response2 = c_iot_data.update_thing_shadow(
        thingName=thing_name,
        payload=shadow_document
    )
    print(response2)
    print("adding room number {} to thing attributes".format(ROOM_NUMBER))
    response3 = c_iot.update_thing(
        thingName=thing_name,
        attributePayload={
            'attributes': {
                'building': building_names[random.randint(0, len(building_names) - 1)],
                'room_number': str(ROOM_NUMBER)
            },
            'merge': True
        },
        removeThingType=False
    )
    print(response3)
    ROOM_NUMBER += 1

    time.sleep(0.5)

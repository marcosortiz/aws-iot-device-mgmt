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

import json
import logging
import requests
import sys
from geopy.distance import great_circle

#http://geopy.readthedocs.io/en/latest/
#https://www.latlong.net/

# Configure logging
logger = logging.getLogger()
#logger.setLevel(logging.INFO)
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter('[%(asctime)s - %(levelname)s - %(funcName)s]: %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

geoip_url = 'http://freegeoip.net/json'

regions = [
    {"name": "ap-southeast-2", "lat": "-33.8", "lon": "151.2"},
    {"name": "us-east-1", "lat": "33.9", "lon": "-77.0"},
    {"name": "us-east-2", "lat": "40.4", "lon": "-82.9"},
    {"name": "us-west-1", "lat": "38.8", "lon": "-120.8"},
    {"name": "eu-central-1", "lat": "50.1", "lon": "8.6"}
]


def get_ip_location():
    r = requests.get(geoip_url)
    j = json.loads(r.text)
    logger.debug("j: {}".format(j))
    return j


j = get_ip_location()
lat = float(j['latitude'])
lon = float(j['longitude'])
logger.info("lat: {}, lon: {}".format(lat, lon))

min_distance = 40000
closest_region = None
for r in regions:
    logger.debug("r: {}".format(r))
    elat = float(r["lat"])
    elon = float(r["lon"])
    logger.debug("elat: {}, elon: {}".format(elat, elon))
    distance = great_circle((lat, lon), (elat, elon)).km
    logger.debug("distance: {}".format(distance))
    if distance <= min_distance:
        min_distance = distance
        closest_region = r["name"]
    logger.debug("min_distance: {}".format(min_distance))

logger.info("closest_region: {}, distance: {}".format(closest_region, min_distance))

#!/usr/bin/env python3

#
# virtual-sensor.py
#


# Copyright 2010-2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

#
# globals
#
haveSense = None
push_interval = 1


#
# import useful stuff
#
try:
    from sense_hat import SenseHat
    haveSense = True
except:
    haveSense = False
    import random

import json
from time import gmtime, strftime

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import sys
import logging
import time
import argparse


# Shadow callback
def sdwCallback(client, userdata, message):
    global push_interval
    shadow_delta_topic = '$aws/things/{}/shadow/update/delta'.format(clientId)
    logger.info("Shadow message on topic: {}".format(message.topic))
    logger.info("payload: {}".format(message.payload))

    if message.topic != shadow_delta_topic:
        return

    logger.info("shadow: message received on delta topic")
    delta = json.loads(message.payload)
    logger.info("delta: {}".format(delta))
    try:
        new_push_interval = delta['state']['push_interval']
        push_interval = new_push_interval
        logger.info("new_push_interval: {}".format(new_push_interval))
        state = { "state": { "reported": { "push_interval": new_push_interval }, "desired": None } }
        shadow_update_topic = '$aws/things/{}/shadow/update'.format(clientId)
        logger.info("reporting state to shadow: {}".format(shadow_update_topic))
        myAWSIoTMQTTClient.publish(shadow_update_topic, json.dumps(state, indent=4), 0)
        client.publish(shadow_update_topic, json.dumps(state, indent=4), 0)
    except Exception as e:
        logger.error("error updating shadow: {}".format(e))


# Custom MQTT message callback
def customCallback(client, userdata, message):
    print("---customCallback---")
    print("client: {}".format(client))
    print("userdata: {}".format(userdata))
    print("Received  message on topic: {}".format(message.topic))
    print(message.payload)
    print("--------------\n\n")


def getSensorData(sense):
    message = {}

    if sense is not None:
        message['sensor'] = 'SenseHat'
        message['temperature'] = sense.get_temperature()
        message['pressure'] = sense.get_pressure()
        message['humidity'] = sense.get_humidity()
    else:
        message['sensor'] = 'Random'
        message['temperature'] = random.uniform(15,35)
        message['pressure'] = random.uniform(30,70)
        message['humidity'] = random.uniform(900,1150)

    return message


# Read in command-line parameters
parser = argparse.ArgumentParser()
parser.add_argument("-e", "--endpoint", action="store", required=True, dest="host", help="Your AWS IoT custom endpoint")
parser.add_argument("-r", "--rootCA", action="store", required=True, dest="rootCAPath", help="Root CA file path")
parser.add_argument("-c", "--cert", action="store", dest="certificatePath", help="Certificate file path")
parser.add_argument("-k", "--key", action="store", dest="privateKeyPath", help="Private key file path")
parser.add_argument("-id", "--clientId", action="store", dest="clientId", default="basicPubSub", help="Targeted client id")
parser.add_argument("-t", "--topic", action="store", dest="topic", default="sdk/test/Python", help="Targeted topic")

args = parser.parse_args()
host = args.host
rootCAPath = args.rootCAPath
certificatePath = args.certificatePath
privateKeyPath = args.privateKeyPath
clientId = args.clientId
topic = args.topic

#
# Shadow
#
shadow_topics = '$aws/things/' + clientId + '/shadow/#'
shadow_update_topic = '$aws/things/' + clientId + '/shadow/update'
state = { "state": { "reported": { "push_interval": push_interval } } }


#
# Configure logging
#
logger = logging.getLogger("AWSIoTPythonSDK.core")
logger.setLevel(logging.INFO)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s - %(levelname)s - %(filename)s:%(lineno)s - %(funcName)s - %(message)s")
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

logger.info("connecting to AWS IoT at endpoint: {}".format(host))

logger.info("rootCAPath: " + rootCAPath)
# iterate through all connection options for the core
coreHost = ""
corePort = ""
numcoreConnections = 0
coreConnections = {}

myAWSIoTMQTTClient = None

myAWSIoTMQTTClient = AWSIoTMQTTClient(clientId)

# AWSIoTMQTTClient connection configuration
myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec
myAWSIoTMQTTClient.configureCredentials(rootCAPath, privateKeyPath, certificatePath)
myAWSIoTMQTTClient.configureEndpoint(host, 8883)

myAWSIoTMQTTClient.connect()
logger.info("subscribe and set customCallback: topic: {}".format(topic))
myAWSIoTMQTTClient.subscribe(topic, 0, customCallback)
time.sleep(2)
logger.info("subscribe and set sdwCallback: topic: {}".format(shadow_topics))
myAWSIoTMQTTClient.subscribe(shadow_topics, 0, sdwCallback)
time.sleep(2)
logger.info("reporting state to shadow: {}".format(shadow_update_topic))
myAWSIoTMQTTClient.publish(shadow_update_topic, json.dumps(state, indent=4), 0)

# sense hat
if haveSense:
    sense = SenseHat()
else:
    sense = None

# Publish to the same topic in a loop forever
loopCount = 0
while True:
    message = getSensorData(sense)

    message['device'] = clientId
    message['datetime'] = time.strftime("%Y-%m-%dT%H:%M:%S", gmtime())
    logger.info(json.dumps(message))
    logger.info("publish to topic: {}".format(topic))
    myAWSIoTMQTTClient.publish(topic, json.dumps(message, indent=4), 0)

    time.sleep(push_interval)

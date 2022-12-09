#!/usr/bin/env python3

import argparse
import boto3
import datetime
import json
import logging
import random
import sys
import time
import uuid


logger = logging.getLogger()
logger.setLevel(logging.INFO)
streamHandler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

def getSensorData():
    message = {}

    message['device_id'] = 'v_sensor_{}'.format(random.randint(10,50))

    message['sensor'] = 'Random'
    #message['time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f000")
    message['time'] = int(round(time.time() * 1000))
    message['temperature'] = random.uniform(15,35)
    message['humidity'] = random.uniform(30,70)
    message['pressure'] = random.uniform(900,1150)

    return json.dumps(message)

parser = argparse.ArgumentParser()
parser.add_argument("-r", action="store", required=True, dest="region", help="AWS region")
parser.add_argument("-i", action="store", type=int, dest="interval", help="interval to send data, default 120", default=120)
parser.add_argument("-k", action="store", required=True, dest="kinesis_stream_name", help="Kinesis data stream name")

args = parser.parse_args()
STREAM_NAME = args.kinesis_stream_name
REGION = args.region
INTERVAL = args.interval

c_kinesis = boto3.client('kinesis', region_name=REGION)

logger.info("sending data every {} seconds".format(INTERVAL))
time.sleep(2)

while True:
    message = getSensorData()
    logger.info("message: {}".format(json.dumps(message, indent=2)))
    response = c_kinesis.put_record(
        StreamName=STREAM_NAME,
        Data=message.encode(),
        PartitionKey='{}'.format(uuid.uuid4())
    )
    logger.info("response: {}\n".format(response))
    time.sleep(INTERVAL)

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

DEVICE_ID = 'sensor01'

def getSensorData():
    message = {}
    
    humidity = random.randint(40, 50)
    temperature = random.randint(temperature_normal, (temperature_normal + 5))
    pressure = random.randint(900, 1000)

    seed = random.randint(1,10)
    time_seed = False
    
    if int(round(time.time())) % 4 == 0:
        time_seed = True
        
    logger.info("seed: {} time_seed: {}".format(seed, time_seed))
    
    if seed == 3 and time_seed:
        logger.info("HIGH")
        humidity = random.randint(70, 100)
        temperature = random.randint(temperature_high, (temperature_high + 15))
        pressure = random.randint(1100, 1200)
    elif seed == 7 and time_seed:
        logger.info("LOW")
        humidity = random.randint(10, 20)
        temperature = random.randint(temperature_low, (temperature_low + 15))
        pressure = random.randint(800, 900)

    #message['device_id'] = 'v_sensor_{}'.format(random.randint(10,50))
    message['device_id'] = DEVICE_ID

    message['sensor'] = 'Random'
    #message['time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f000")
    message['time'] = int(round(time.time() * 1000))
    message['temperature'] = temperature
    message['humidity'] = humidity
    message['pressure'] = pressure

    return json.dumps(message)

parser = argparse.ArgumentParser()
parser.add_argument("-r", action="store", required=True, dest="region", help="AWS region")
parser.add_argument("-i", action="store", dest="interval", help="interval to send data, default 1", type=int, default=1)
parser.add_argument("-k", action="store", required=True, dest="kinesis_stream_name", help="Kinesis data stream name")

args = parser.parse_args()
STREAM_NAME = args.kinesis_stream_name
REGION = args.region
INTERVAL = args.interval

c_kinesis = boto3.client('kinesis', region_name=REGION)

logger.info("sending data every {} seconds".format(INTERVAL))
time.sleep(2)

temperature_normal = random.randint(20, 40)
temperature_high = random.randint(80,100)
temperature_low = random.randint(1,15)

logger.info("temperature_normal: {} temperature_high: {} temperature_low: {}".format(temperature_normal, temperature_high, temperature_low))

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

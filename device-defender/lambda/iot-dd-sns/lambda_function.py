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


import boto3
import json
import logging
import time
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

#
# globals
#
root_ca_cert = "root.ca.bundle.pem"
device_key = "disconnect.private.key"
device_cert = "disconnect.certificate.pem"

#
# logging
#

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# connect to AWS IoT
def connect_to_iot(thing_name, iot_endpoint):
    logger.info("connecting to AWS iot with thing_name: {}".format(thing_name))
    
    MQTTClient = None

    MQTTClient = AWSIoTMQTTClient(thing_name)
    
    # AWSIoTMQTTClient connection configuration
    MQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
    MQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
    MQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
    MQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
    MQTTClient.configureMQTTOperationTimeout(5)  # 5 sec
    MQTTClient.configureCredentials(root_ca_cert, device_key, device_cert)
    MQTTClient.configureEndpoint(iot_endpoint, 8883)
    
    logger.info("connect")
    MQTTClient.connect()
    
    time.sleep(2)
    
    logger.info("disconnect")
    MQTTClient.disconnect()


# revoke certificate from a thing
def disable_thing(thing_name):
    # cert_new_status = 'REVOKED'
    cert_new_status = 'INACTIVE'
    
    logger.info("disabling thing_name: {} cert_new_status: {}".format(thing_name, cert_new_status))
    
    c_iot = boto3.client('iot')

    # iot endpoint
    response = c_iot.describe_endpoint()
    iot_endpoint = response['endpointAddress']
    logger.info("iot_endpoint: {}".format(iot_endpoint))

    principals = c_iot.list_thing_principals(thingName=thing_name)
    
    for arn in principals['principals']:
        cert_id = arn.split('/')[1]
        logger.info("revoke: cert_id: {} arn: {}".format(cert_id, arn))
        
        response = c_iot.update_certificate(certificateId=cert_id,newStatus=cert_new_status)
        logger.info("REVOKED: {}".format(response))
    
    connect_to_iot(thing_name, iot_endpoint)


def lambda_handler(event, context):
    # TODO implement
    logger.info("event: {}".format(event))
    
    for record in event['Records']:
        message_str = record['Sns']['Message']
        logger.info("message_str: {}".format(message_str))
        message = json.loads(message_str)
        
        event_type = message['violationEventType']
        logger.info("event_type: {}".format(event_type))
        if event_type == 'in-alarm':
            thing_name = message['thingName']
            logger.info("thing_name: {}".format(thing_name))
            disable_thing(thing_name)
    return 'Device Defender SNS'

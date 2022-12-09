#!/usr/bin/env python3.7

# coding: utf-8

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

# IoT Job Agent
#
# Sample agent which handles IoT jobs.
#

# Libraries, Logging
import argparse
import AWSIoTPythonSDK
import json
import logging
import os
import re
import time
import sys
import tarfile
import urllib3
import uuid
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from AWSIoTPythonSDK.core.greengrass.discovery.providers import DiscoveryInfoProvider
from AWSIoTPythonSDK.core.protocol.connection.cores import ProgressiveBackOffCore
from AWSIoTPythonSDK.exception.AWSIoTExceptions import DiscoveryInvalidRequestException
from time import localtime, strftime
from datetime import timedelta

MAX_DISCOVERY_RETRIES = 10
GROUP_CA_PATH = "./greengrassCA/"

# Configure logging
logger = logging.getLogger("AWSIoTPythonSDK.core")
#logger.setLevel(logging.DEBUG)
logger.setLevel(logging.INFO)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s - %(levelname)s - %(filename)s:%(lineno)s - %(funcName)s - %(message)s")
#formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

#
# parse command line args
#
parser = argparse.ArgumentParser(description='Sample job agent for AWS IoT Device Management')
parser.add_argument("-c", "--client-id", action="store", required=True, dest="client_id",
                    help="Name of your device. The client-id is also used in the job topics.")
parser.add_argument("-i", "--iot-endpoint", action="store", required=True, dest="iot_endpoint",
                    help="AWS IoT Endpoint (host) where the job agent connects to.")
parser.add_argument("--cacert", action="store", required=True, dest="root_ca_cert",
                    help="CA that signed the server certificate from AWS IoT Core.")
parser.add_argument("--cert", action="store", required=True, dest="device_cert",
                    help="Device certificate.")
parser.add_argument("--key", action="store", required=True, dest="device_key",
                    help="Device private key.")
parser.add_argument("--connect-to", action="store", dest="connect_to", 
                    default="awsiot", help="Where to connect to. Can be either awsiot or greengrass")


args = parser.parse_args()
client_id = args.client_id
iot_endpoint = args.iot_endpoint
root_ca_cert = args.root_ca_cert
device_cert = args.device_cert
device_key = args.device_key
connect_to = args.connect_to

def callback_jobs_get_rejected(client, userdata, message):
    #logger.info("client: {}".format(client))
    #logger.info("userdata: {}".format(userdata))
    logger.info("message on topic: {}".format(message.topic))
    logger.info(message.payload + "\n")

def callback_jobs_get_accepted(client, userdata, message):
    logger.info("message on topic: {}".format(message.topic))
    logger.info(message.payload)

    payload = json.loads(message.payload)

    if "queuedJobs" in payload:
        time.sleep(2)
        for job in payload["queuedJobs"]:
            logger.info("job: {}".format(job))
        time.sleep(2)

        if len(payload["queuedJobs"]) >= 1:
            logger.info("JOBS AVAILABLE")
            logger.info("found {} queued jobs".format(payload["queuedJobs"]))
            time.sleep(5)
            client_token = str(uuid.uuid4())
            job_id = payload["queuedJobs"][0]["jobId"]
            logger.info("taking job with job_id: {}".format(job_id))
            time.sleep(5)
            message = { "clientToken": client_token }
            topic = '$aws/things/' + client_id + '/jobs/' + job_id + '/get'
            logger.info("DescribeJobExecution: publish: topic: {} message: {}".format(topic, message))
            myAWSIoTMQTTClient.publish(topic, json.dumps(message), 0)
            time.sleep(2)
        else:
            logger.info("NO jobs available")
            time.sleep(1)

def callback_job_id_get_accepted(client, userdata, message):
    #logger.info("client: {}".format(client))
    #logger.info("userdata: {}".format(userdata))
    logger.info("message on topic: {}".format(message.topic))
    logger.info(message.payload)

    payload = json.loads(message.payload)

    if "execution" in payload:
        if "status" in payload["execution"] and payload["execution"]["status"] == "QUEUED":
            if "jobDocument" in payload["execution"]:
                logger.info("found job document, calling job document processor")
                time.sleep(5)
                process_job_document(payload["execution"]["jobId"], payload["execution"]["jobDocument"])
        else:
            logger.warn("job in status {} will not be processed".format(payload["execution"]["status"]))
            time.sleep(1)


def callback_jobs_notify_next(client, userdata, message):
    #logger.info("client: {}".format(client))
    #logger.info("userdata: {}".format(userdata))
    logger.info("message on topic: {}".format(message.topic))
    logger.info(message.payload)

def callback_job_id_update(client, userdata, message):
    logger.info("message on topic: {}".format(message.topic))
    logger.info(message.payload)

def ack_callback_subscribe(mid, data):
    logger.info("mid: {} data: {}".format(mid, data))

def ack_callback_unsubscribe(mid):
    logger.info("mid: {}".format(mid))

def process_job_document(job_id, job_document):
    logger.info("job_id: {} job_document: {}".format(job_id, job_document))
    time.sleep(2)

    # subscribe to update topix for a certain job_id
    topic_update_job = '$aws/things/' + client_id + '/jobs/' + str(job_id) + '/update/#'
    logger.info("UpdateJobExecution: receive responses: subcribeAsync to topic {}".format(topic_update_job))
    packet_id = myAWSIoTMQTTClient.subscribeAsync(topic_update_job, 0, ackCallback=ack_callback_subscribe, messageCallback=callback_job_id_update)
    logger.info("packet_id: {}".format(packet_id))
    time.sleep(2)

    # update_job_execution
    topic_job_exec_update = '$aws/things/' + client_id + '/jobs/' + str(job_id) + '/update'
    client_token = str(uuid.uuid4())
    message = {
        "status": "IN_PROGRESS",
        "clientToken": client_token
    }
    logger.info("UpdateJobExecution: topic: {} message: {}".format(topic_job_exec_update, message))
    myAWSIoTMQTTClient.publish(topic_job_exec_update, json.dumps(message), 0)
    time.sleep(2)

    logger.info("operation: {}".format(job_document["operation"]))

    # sys-info: report uptime
    if job_document["operation"] == "sys-info":
        upt_msg = { "thing-id": client_id, "uptime": uptime() }
        logger.info("PUBLISH UPTIME - topic: {} message: {}".format(job_document["topic"], upt_msg))
        myAWSIoTMQTTClient.publish(job_document["topic"], json.dumps(upt_msg), 0)
        time.sleep(5)

        message = {
            "status": "SUCCEEDED",
            "clientToken": client_token
        }

    # install software by unpacking tar file
    elif job_document["operation"] == "install":
        url = job_document["software"]["url"]
        directory = job_document["software"]["directory"]
        version = job_document["software"]["version"]
        logger.info("url: {} directory: {} version: {}".format(url, directory, version))

        if install_software(url, directory, version):
            message = {
                "status": "SUCCEEDED",
                "clientToken": client_token
            }
        else:
            message = {
                "status": "FAILED",
                "clientToken": client_token
            }
    elif job_document["operation"] == "rollback":
        directory = job_document["software"]["directory"]
        to_version = job_document["software"]["to-version"]
        logger.info("directory: {} to_version: {}".format(directory, to_version))

        if rollback_software(directory, to_version):
            message = {
                "status": "SUCCEEDED",
                "clientToken": client_token
            }
        else:
            message = {
                "status": "FAILED",
                "clientToken": client_token
            }

    else:
        logger.error("unknown operation")
        message = {
            "status": "REJECTED",
            "clientToken": client_token
        }

    logger.info("UpdateJobExecution: topic: {} message: {}".format(topic_job_exec_update, message))
    myAWSIoTMQTTClient.publish(topic_job_exec_update, json.dumps(message), 0)
    time.sleep(2)

    packet_id = myAWSIoTMQTTClient.unsubscribeAsync(topic_update_job, ackCallback=ack_callback_unsubscribe)
    logger.info("packet_id: {}".format(packet_id))
    time.sleep(2)

# function to get system uptime
def uptime():
  with open('/proc/uptime', 'r') as file:
    return str(timedelta(seconds = float(file.readline().split()[0])))


def install_software(url, directory, version):
    local_tar = '/tmp/software-' + strftime("%Y%m%d%H%M%S", localtime()) + '.tar.gz'
    directory_version = directory + '/' + version
    directory_current = directory + '/current'
    logger.info("local_tar: {}".format(local_tar))

    http = urllib3.PoolManager()
    r = http.request('GET', url)
    logger.info("HTTP status: {}".format(r.status))

    if r.status != 200:
        logger.error("HTTP status not equal 200")
        return False

    f = open(local_tar, "w")
    f.write(r.data)
    f.close()

    if not os.path.isdir(directory_version):
        logger.info("create directory {}".format(directory_version))
        try:
            os.makedirs(directory_version, mode=0o755)
        except Exception as e:
            logger.error("failed to create directory {}: {}".format(directory_version, e))
            return False

    logger.info("extract tarball to directory {}".format(directory_version))
    tar = tarfile.open(local_tar)
    tar.extractall(path=directory_version)
    tar.close()

    logger.info("create symlink from {} -> {}".format(directory_version, directory_current))
    try:
        if os.path.lexists(directory_current):
            os.remove(directory_current)
        os.symlink(directory_version, directory_current)
        return True
    except Exception as e:
        logger.error("could not create symlink: {}".format(e))
        return False


def rollback_software(directory, to_version):
    directory_to_version = directory + '/' + to_version
    directory_current = directory + '/current'
    logger.info("directory_to_version: {}".format(directory_to_version))

    if not os.path.isdir(directory_to_version):
        logger.error("rollback directory {} does not exist".format(directory_to_version))
        return False

    logger.info("create symlink from {} -> {}".format(directory_to_version, directory_current))
    try:
        if os.path.lexists(directory_current):
            os.remove(directory_current)
        os.symlink(directory_to_version, directory_current)
        return True
    except Exception as e:
        logger.error("could not create symlink: {}".format(e))
        return False




# Init AWSIoTMQTTClient
myAWSIoTMQTTClient = None
myAWSIoTMQTTClient = AWSIoTMQTTClient(client_id)
myAWSIoTMQTTClient.configureEndpoint(iot_endpoint, 8883)
myAWSIoTMQTTClient.configureCredentials(root_ca_cert, device_key, device_cert)

# AWSIoTMQTTClient connection configuration
myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec

# Greengrass discovery
if connect_to == "greengrass":
    logger.info("connecting to greengrass - starting discovery")
    # Progressive back off core
    backOffCore = ProgressiveBackOffCore()
    
    discovery_host = re.sub(r'^.+\.iot', 'greengrass-ats.iot', iot_endpoint)
    
    # Discover GGCs
    discoveryInfoProvider = DiscoveryInfoProvider()
    discoveryInfoProvider.configureEndpoint(discovery_host)
    discoveryInfoProvider.configureCredentials(root_ca_cert, device_cert, device_key)
    discoveryInfoProvider.configureTimeout(10)  # 10 sec
    
    retryCount = MAX_DISCOVERY_RETRIES
    discovered = False
    groupCA = None
    coreInfo = None
    while retryCount != 0:
        try:
            discoveryInfo = discoveryInfoProvider.discover(client_id)
            caList = discoveryInfo.getAllCas()
            coreList = discoveryInfo.getAllCores()
    
            # We only pick the first ca and core info
            groupId, ca = caList[0]
            coreInfo = coreList[0]
            logger.info("discovered GGC: {} group: {}".format(coreInfo.coreThingArn, groupId))
    
            groupCA = GROUP_CA_PATH + groupId + "_CA_" + str(uuid.uuid4()) + ".crt"
            logger.info("storing groupCA at: {}".format(groupCA))
            if not os.path.exists(GROUP_CA_PATH):
                os.makedirs(GROUP_CA_PATH)
            groupCAFile = open(groupCA, "w")
            groupCAFile.write(ca)
            groupCAFile.close()
    
            discovered = True
            print("Now proceed to the connecting flow...")
            break
        except DiscoveryInvalidRequestException as e:
            print("Invalid discovery request detected!")
            print("Type: %s" % str(type(e)))
            print("Error message: %s" % e.message)
            print("Stopping...")
            break
        except BaseException as e:
            print("Error in discovery!")
            print("Type: %s" % str(type(e)))
            print("Error message: %s" % e.message)
            print(format(e))
            retryCount -= 1
            print("\n%d/%d retries left\n" % (retryCount, MAX_DISCOVERY_RETRIES))
            print("Backing off...\n")
            backOffCore.backOff()
    
    if not discovered:
        print("Discovery failed after %d retries. Exiting...\n" % (MAX_DISCOVERY_RETRIES))
        sys.exit(-1)
        
    logger.info("coreInfo: {}".format(coreInfo))
    print(coreInfo.connectivityInfoList)
    print(groupCA)
    root_ca_cert = groupCA
    myAWSIoTMQTTClient.configureCredentials(groupCA, device_key, device_cert)

    connected = False
    for connectivityInfo in coreInfo.connectivityInfoList:
        currentHost = connectivityInfo.host
        currentPort = connectivityInfo.port
        logger.info("GG connecting: endpoint: {}:{} client_id: {}".format(currentHost, currentPort, client_id))
        time.sleep(1)
        myAWSIoTMQTTClient.configureEndpoint(currentHost, currentPort)
        try:
            myAWSIoTMQTTClient.connect()
            connected = True
            break
        except BaseException as e:
            print("Error in connect!")
            print("Type: %s" % str(type(e)))
            print("Error message: %s" % e.message)
    
    if not connected:
        print("Cannot connect to core %s. Exiting..." % coreInfo.coreThingArn)
        sys.exit(-2)

else:
    # Connect to AWS IoT
    logger.info("connecting: endpoint {}: client_id: {}".format(iot_endpoint, client_id))
    time.sleep(1)
    # Connect and subscribe to AWS IoT
    myAWSIoTMQTTClient.connect()


# Subscribe to the Job Topics

get_jobs_accepted_topic = '$aws/things/' + client_id + '/jobs/get/accepted'
get_jobs_rejected_topic = '$aws/things/' + client_id + '/jobs/get/rejected'
get_job_id_accepted_topic = '$aws/things/' + client_id + '/jobs/+/get/accepted'
jobs_notify_next_topic = '$aws/things/' + client_id + '/jobs/notify-next'

logger.info("GetPendingJobExecutions - subscribe: topics: {}, {}, {}, {}".format(
    get_jobs_accepted_topic, get_jobs_rejected_topic, get_job_id_accepted_topic, jobs_notify_next_topic))

try:
    myAWSIoTMQTTClient.subscribe(get_jobs_accepted_topic, 0, callback_jobs_get_accepted)
    myAWSIoTMQTTClient.subscribe(get_jobs_rejected_topic, 0, callback_jobs_get_rejected)
    myAWSIoTMQTTClient.subscribe(get_job_id_accepted_topic, 0, callback_job_id_get_accepted)
    myAWSIoTMQTTClient.subscribe(jobs_notify_next_topic, 0, callback_jobs_notify_next)
    time.sleep(2)
    logger.info("done subscribing")
except Exception as e:
    logger.error("failed to subscribe to topics: {}".format(e))



# endless loop to get pending jobs
while True:
    client_token = str(uuid.uuid4())
    get_pending_jobs_execution_topic = '$aws/things/' + client_id + '/jobs/get'
    get_pending_jobs_execution_message = { "clientToken": client_token }

    try:
        logger.info("GetPendingJobExecutions: topic: {} message: {}".format(get_pending_jobs_execution_topic, get_pending_jobs_execution_message))
        myAWSIoTMQTTClient.publish(get_pending_jobs_execution_topic, json.dumps(get_pending_jobs_execution_message), 0)
        time.sleep(2)
    except Exception as e:
        logger.error("GetPendingJobExecutions - publish failed: {}".format(e))

    time.sleep(15)


myAWSIoTMQTTClient.unsubscribe(get_jobs_accepted_topic)
myAWSIoTMQTTClient.unsubscribe(get_jobs_rejected_topic)
myAWSIoTMQTTClient.unsubscribe(jobs_notify_next_topic)

myAWSIoTMQTTClient.disconnect()

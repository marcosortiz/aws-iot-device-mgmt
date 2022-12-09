#!/usr/bin/env python3

# tunnel-manager.py
# Tunnel manager for AWS IoT Secured Tunneling
#
# install required packages
# pip3 install boto3

import argparse
import json
import logging
import os
import subprocess
import sys
import time

from datetime import datetime
from threading import Timer

import boto3

#
# configure logging
#
#logger = logging.getLogger("AWSIoTPythonSDK.core")
logger = logging.getLogger()
logger.setLevel(logging.INFO)
streamHandler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(filename)s:%(lineno)s - %(funcName)s: %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', None)
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', None)

# Constants
tunnel_processes = {}
app_endpoint = None
local_proxy = None
local_port = None
c_iot_data = None
c_iot_sec_tun = None

def open_tunnel(endpoint, port, tunnel_lifetime, region, topic):
    try:
        # Open tunnel and set important response values
        response = c_iot_sec_tun.open_tunnel(timeoutConfig={'maxLifetimeTimeoutMinutes': tunnel_lifetime})
        print("response: {}".format(response))
        tunnel_id = response['tunnelId']
        source_cat = response['sourceAccessToken']
        destination_cat = response['destinationAccessToken']

        print("tunnel_id: {}".format(tunnel_id))

        msg_dst = {
          "state": {
            "desired": {
              "tunnel": "start",
              "tunnel_lifetime": tunnel_lifetime,
              "endpoint": endpoint,
              "region": region,
              "access_token": destination_cat
            }
          }
        }

        print("publish: topic: {}\n         message: {}".format(topic, msg_dst))
        #print(json.dumps(msg_gg_core, indent=4))

        response = c_iot_data.publish(topic=topic, qos=1, payload=json.dumps(msg_dst))
        logger.info('response: {}'.format(response))

        os.environ["AWSIOT_TUNNEL_ACCESS_TOKEN"] = source_cat

        #os_cmd = '{} -s -p {} -e proxy.envoy-gamma.us-east-1.amazonaws.com -t {}'.format(local_proxy, local_port, source_cat)
        os_cmd = '{} -s {} -r {} -k'.format(local_proxy, local_port, region)

        logger.info('os_cmd: {}'.format(os_cmd))
        os.system(os_cmd)
        #p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        #print('pid: {}'.format(p.pid))
        #time.sleep(30)

    except Exception as e:
        logger.error('error opening tunnel: {}'.format(e))


if __name__ == "__main__":
    #
    # parse command line args
    #
    parser = argparse.ArgumentParser(description='Manager for IoT DM tunnels')
    parser.add_argument("--local-proxy", action="store", required=True, dest="local_proxy", help="local proxy executable incl. path")
    parser.add_argument("-p", "--local-port", action="store", required=True, dest="local_port", default=2299, help="local port where the proxy listens, defaul 2299")
    parser.add_argument("--region-iot", action="store", required=True, dest="region_name_iot", help="aws region where to publish the message")
    parser.add_argument("--region-tun", action="store", required=True, dest="region_name_tun", help="aws region where to create the tunnel")
    parser.add_argument("--profile-iot", action="store", dest="profile_iot", default="default", help="profile to use to access AWS IoT data")
    parser.add_argument("--profile-tun", action="store", dest="profile_tun", default="default", help="profile to use for AWS IoT secured tunneling")
    parser.add_argument("-e", "--app-endpoint", action="store", required=True, dest="app_endpoint", help="app endpoint where the destination proxy should tunnel to, e.g. localhost:22 for ssh")
    parser.add_argument("-t", "--topic", action="store", required=True, dest="topic", help="topic to publish dest message to")
    parser.add_argument("-l", "--tunnel-lifetime", action="store", dest="tunnel_lifetime", default=60, help="tunnel lifetime in minutes")

    args = parser.parse_args()
    local_proxy = args.local_proxy
    local_port = args.local_port
    region_name_iot = args.region_name_iot
    region_name_tun = args.region_name_tun
    profile_iot = args.profile_iot
    profile_tun = args.profile_tun
    app_endpoint = args.app_endpoint
    topic = args.topic
    tunnel_lifetime = int(args.tunnel_lifetime)

    logger.info("app_endpoint: {} local_proxy: {} local_port: {} topic: {} tunnel_lifetime: {}".format(app_endpoint, local_proxy, local_port, topic, tunnel_lifetime))
    logger.info("region_name_iot: {} region_name_tun: {} profile_iot: {} profile_tun: {}".format(region_name_iot, region_name_tun, profile_iot, profile_tun))

    # create clients
    try:
        # iotsecuretunneling
        sess_iot_sec_tun = boto3.Session(profile_name=profile_tun)
        c_iot_sec_tun = sess_iot_sec_tun.client(service_name='iotsecuretunneling', region_name=region_name_tun)

        # boto3 session and iot clients
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            logger.info('session: using credentials from environment variables')
            session = boto3.Session(
                aws_access_key_id=AWS_ACCESS_KEY_ID, 
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY
            )
        else:
            logger.info('session: using profile %s', profile_iot)
            session = boto3.Session(profile_name=profile_iot)

        c_iot = session.client(
            service_name='iot',
            region_name=region_name_iot
        )
        iot_data_endpoint = c_iot.describe_endpoint(
            endpointType='iot:Data-ATS')['endpointAddress']
        c_iot_data = session.client(
            service_name='iot-data',
            region_name=region_name_iot,
            endpoint_url=f'https://{iot_data_endpoint}'
        )

    except Exception as e:
        logger.error('error creating clients: {}'.format(e))

    logger.info("calling open_tunnel")
    open_tunnel(app_endpoint, local_port, tunnel_lifetime, region_name_tun, topic)

#!/usr/bin/env python3

# coding: utf-8

# listener-agent.py
# Listener agent for AWS IoT Secured Tunneling
#
# install required packages
# pip3 install python-daemon
# pip3 install AWSIoTPythonSDK
# run with: /tunnel-managerd.py -e a1xrd8yavpilkd-ats.iot.eu-west-2.amazonaws.com -r ~/root.ca.bundle.pem -c tunnel-manager-001.certificate.pem -k tunnel-manager-001.private.key -l ./local_proxy_linux -id tunnel-manager-001
#

import argparse
import daemon
import daemon.pidfile
import json
import lockfile
import logging
import os
import signal
import subprocess
import sys
import time
import uuid

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
from time import gmtime, strftime
from datetime import datetime
from threading import Timer

# globals
log_file = '/tmp/listener-agent.log'
pid_file = '/tmp/listener-agent.pid'
tunnel_processes = {}
tunnel_processes_monitor_interval = 30
mqtt_qos = 1


#
# configure logging
#
#logger = logging.getLogger("AWSIoTPythonSDK.core")
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = logging.FileHandler(log_file)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(filename)s:%(lineno)s - %(funcName)s: %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

#
# parse command line args
#
parser = argparse.ArgumentParser()
parser.add_argument("-e", "--endpoint", action="store", required=True, dest="host", help="Your AWS IoT custom endpoint")
parser.add_argument("-r", "--rootCA", action="store", required=True, dest="root_ca", help="Root CA file path")
parser.add_argument("-l", "--local-proxy", action="store", required=True, dest="local_proxy", help="local proxy executable")
parser.add_argument("-c", "--cert", action="store", dest="certificatePath", help="Certificate file path")
parser.add_argument("-k", "--key", action="store", dest="privateKeyPath", help="Private key file path")
parser.add_argument("-w", "--websocket", action="store_true", dest="useWebsocket", default=False, help="Use MQTT over WebSocket")
parser.add_argument("-id", "--client_id", action="store", required=True, dest="client_id", help="Targeted client id")
#parser.add_argument("-t", "--topic", action="store", required=True, dest="topic", help="topic to publish dest message to")


args = parser.parse_args()
host = args.host
root_ca = args.root_ca
local_proxy = args.local_proxy
certificatePath = args.certificatePath
privateKeyPath = args.privateKeyPath
useWebsocket = args.useWebsocket
client_id = args.client_id
client_id_sdw = '{}_sdw'.format(client_id)
#topic = args.topic
topic = 'cmd/sectunnel/{}/resp'.format(client_id)

c_mqtt = None
c_mqtt_sdw = None
device_shadow = None


if not os.access(local_proxy, os.X_OK):
    raise Exception('local proxy excutable "{}" is not executable or does not exist'.format(local_proxy))
    sys.exit(1)


def adjust_tunnel_lifetime(tunnel_lifetime, timestamp):
    now = int(time.time())
    adjust_sec = now - timestamp
    adjust_min = adjust_sec / 60
    adjusted_tunnel_lifetime = tunnel_lifetime - adjust_min
    logger.info('tunnel_lifetime: {} now: {} timestamp: {} adjust_sec: {} adjust_min: {} adjusted_tunnel_lifetime: {}'.format(tunnel_lifetime, now, timestamp, adjust_sec, adjust_min, adjusted_tunnel_lifetime))

    return adjusted_tunnel_lifetime


def shadow_handler_get(payload, response_status, token):
    logger.info('payload: {}, response_status: {}, token: ***'.format(payload, response_status))
    logger.debug('payload: {}, response_status: {}, token: {}'.format(payload, response_status, token))
    # payload is a JSON string ready to be parsed using json.loads(...)
    # in both Py2.x and Py3.x
    if response_status == "timeout":
        logger.info("update request timeout: token: ***")
        logger.debug("update request timeout: token: {}".format(token))

    if response_status == "accepted":
        payload_dict = json.loads(payload)
        logger.info('update request accepted: payload_dict: {} token: ***'.format(payload_dict))
        logger.debug('update request accepted: payload_dict: {} token: {}'.format(payload_dict, token))

        if 'state' in payload_dict and 'delta' in payload_dict['state'] and \
           'tunnel' in payload_dict['state']['desired'] and \
           payload_dict['state']['desired']['tunnel'] == 'start' and \
           'access_token' in payload_dict['state']['desired'] and \
           'tunnel_lifetime' in payload_dict['state']['desired'] and \
           'region' in payload_dict['state']['desired'] and \
           'endpoint' in payload_dict['state']['desired']:

            os.environ["AWSIOT_TUNNEL_ACCESS_TOKEN"] = payload_dict['state']['desired']['access_token']

            adjusted_tunnel_lifetime = adjust_tunnel_lifetime(payload_dict['state']['desired']['tunnel_lifetime'],
                                                             payload_dict['metadata']['desired']['tunnel_lifetime']['timestamp'])

            local_proxy_cmd = [local_proxy, '-d', payload_dict['state']['desired']['endpoint'],
                              '-r', payload_dict['state']['desired']['region']]
            logger.info('local_proxy_cmd: {} tunnel_lifetime: {} adjust_tunnel_lifetime: {}'.format(local_proxy_cmd, payload_dict['state']['desired']['tunnel_lifetime'], adjusted_tunnel_lifetime))
            start_tunnel(local_proxy_cmd, adjusted_tunnel_lifetime)
            update_msg = '{"state": {"reported": {"status": "tunnel start initiated"}, "desired": null}}'
            device_shadow.shadowUpdate(update_msg, shadow_handler_update, 5)

        else:
            msg = {'status': 'INFO', 'message': 'no desired status: token: {}'.format(token)}
            logger.info({'status': 'INFO', 'message': 'no desired status: token: ***'})
            logger.debug(msg)
            c_mqtt.publish(topic, json.dumps(msg), mqtt_qos)

    if response_status == "rejected":
        logger.warn("update request rejected: token: {}".format(token))


def shadow_handler_delta(payload, response_status, token):
    try:
        logger.info('payload: ***, response_status: {}, token: ***'.format(response_status))
        logger.debug('payload: {}, response_status: {}, token: {}'.format(payload, response_status, token))
        payload_dict = json.loads(payload)
        logger.info('payload_dict: ***')
        logger.debug('payload_dict: {}'.format(payload_dict))

        if 'tunnel' in payload_dict['state'] and \
           payload_dict['state']['tunnel'] == 'start' and \
           'access_token' in payload_dict['state'] and \
           'tunnel_lifetime' in payload_dict['state'] and \
           'region' in payload_dict['state'] and \
           'endpoint' in payload_dict['state']:

            os.environ["AWSIOT_TUNNEL_ACCESS_TOKEN"] = payload_dict['state']['access_token']

            adjusted_tunnel_lifetime = adjust_tunnel_lifetime(payload_dict['state']['tunnel_lifetime'],
                                                              payload_dict['metadata']['tunnel_lifetime']['timestamp'])

            local_proxy_cmd = [local_proxy, '-d', payload_dict['state']['endpoint'],
                               '-r', payload_dict['state']['region']]
            logger.info('local_proxy_cmd: {} tunnel_lifetime: {} adjust_tunnel_lifetime: {}'.format(local_proxy_cmd, payload_dict['state']['tunnel_lifetime'], adjusted_tunnel_lifetime))
            start_tunnel(local_proxy_cmd, adjusted_tunnel_lifetime)
            update_msg = '{"state": {"reported": {"status": "tunnel start initiated"}, "desired": null}}'
            device_shadow.shadowUpdate(update_msg, shadow_handler_update, 5)

        else:
            msg = {'status': 'INFO', 'message': 'delta not for tunnel start'}
            logger.info(msg)
            c_mqtt.publish(topic, json.dumps(msg), mqtt_qos)


        logger.info('state: ***')
        logger.debug('state: {}'.format(payload_dict['state']))
    except Exception as e:
        logger.error('{}'.format(e))


def shadow_handler_update(payload, response_status, token):
    logger.info('payload: {}, response_status: {}, token: ***'.format(payload, response_status))
    logger.debug('payload: {}, response_status: {}, token: {}'.format(payload, response_status, token))


def mqtt_init():
    global c_mqtt, c_mqtt_sdw, device_shadow
    try:
        c_mqtt_sdw = AWSIoTMQTTShadowClient(client_id)
        c_mqtt_sdw.configureEndpoint(host, 8883)
        c_mqtt_sdw.configureCredentials(root_ca, privateKeyPath, certificatePath)
        c_mqtt_sdw.configureConnectDisconnectTimeout(10)  # 10 sec
        c_mqtt_sdw.configureMQTTOperationTimeout(5)  # 5 sec

        if c_mqtt_sdw.connect():
            logger.info('c_mqtt_sdw: connected to endpoint: {}'.format(host))
            time.sleep(2)
        else:
            logger.error('c_mqtt_sdw: failed to connect to endpoint: {}'.format(host))
            sys.exit()

        c_mqtt = c_mqtt_sdw.getMQTTConnection()
        time.sleep(2)
        device_shadow = c_mqtt_sdw.createShadowHandlerWithName(client_id, True)
        # Shadow operations

        update_msg = '{"state": {"reported": {"status": "ready"}}}'
        device_shadow.shadowUpdate(update_msg, shadow_handler_update, 5)
        device_shadow.shadowGet(shadow_handler_get, 5)
        #device_shadow.shadowUpdate(myJSONPayload, customCallback, 5)
        #device_shadow.shadowDelete(customCallback, 5)
        device_shadow.shadowRegisterDeltaCallback(shadow_handler_delta)
        #device_shadow.shadowUnregisterDeltaCallback()

    except Exception as e:
        logger.error(e)
        sys.exit()


def start_tunnel(cmd, tunnel_lifetime):
    global tunnel_processes
    try:
        logger.info('trying to start tunnel proxy with command {}'.format(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        logger.info('tunnel proxy started with pid {}'.format(p.pid))

        # Create expiry details (utc from timestamp)
        now = int(time.time())
        tunnel_expire_time =  now + (tunnel_lifetime * 60)
        logger.info('tunnel_expire_time: {} now: {}'.format(tunnel_expire_time, now))

        tunnel_processes[p.pid] = {'tunnel_expire_time': tunnel_expire_time, 'process': p, 'cmd': cmd}

        msg = {'status': 'SUCCESS', 'message':
               'tunnel started, expires at {}'.format(datetime.utcfromtimestamp(tunnel_expire_time).strftime('%Y-%m-%d %H:%M:%S UTC'))}
        logger.info(msg)

        c_mqtt.publish(topic, json.dumps(msg), mqtt_qos)

    except Exception as e:
        msg = 'failed to start secured tunnel: {}'.format(e)
        logger.error(msg)
        c_mqtt.publish(topic, json.dumps({'status': 'ERROR', 'message': msg}), mqtt_qos)


def monitor_tunnel_processes():
    global tunnel_processes

    tunnel_list = []

    try:
        if not tunnel_processes:
            msg = 'no tunnel processes running'
            logger.info(msg)
            #c_mqtt.publish(topic, json.dumps({'status': 'INFO', 'message': msg}), mqtt_qos)
        else:
            for pid in tunnel_processes.keys():
                msg = 'checking tunnel process with pid: {}'.format(pid)
                logger.info(msg)
                #c_mqtt.publish(topic, json.dumps({'status': 'INFO', 'message': msg}), mqtt_qos)

                now = int(time.time())
                remaining_minutes = (tunnel_processes[pid]['tunnel_expire_time'] - now) / 60
                logger.info('now: {} remaining_minutes: {}'.format(now, remaining_minutes))

                if tunnel_processes[pid]['process'].poll() is None:
                    if  remaining_minutes < 1:
                        msg = 'tunnel expired, will be killed: pid: {} now: {} tunnel_expire_time: {}'.format(pid, now, tunnel_processes[pid]['tunnel_expire_time'])
                        logger.info(msg)
                        #c_mqtt.publish(topic, json.dumps({'status': 'INFO', 'message': msg}), mqtt_qos)
                        tunnel_processes[pid]['process'].kill()
                        tunnel_list.append({"pid": pid, "remaining_minutes": remaining_minutes, "status": "to be killed"})
                    else:
                        msg = 'tunnel still running: pid: {} remaining minutes: {}'.format(pid, remaining_minutes)
                        logger.info(msg)
                        #c_mqtt.publish(topic, json.dumps({'status': 'INFO', 'message': msg}), mqtt_qos)
                        tunnel_list.append({"pid": pid, "remaining_minutes": remaining_minutes, "status": "running"})
                else:
                    if remaining_minutes > 1:
                        # no process but tunnel lifetime not expired
                        # tunnel might have been crashed
                        # restart it
                        msg = 'no tunnel process with pid {} but remaining time is positive, try to restart tunnel'.format(pid)
                        logger.warn(msg)
                        #c_mqtt.publish(topic, json.dumps({'status': 'WARN', 'message': msg}), mqtt_qos)
                        start_tunnel(tunnel_processes[pid]['cmd'], remaining_minutes)
                        tunnel_list.append({"pid": pid, "remaining_minutes": remaining_minutes, "status": "crashed restarting"})

                    # process has stopped, get final output and log
                    stdout, stderr = tunnel_processes[pid]['process'].communicate()
                    msg = 'tunnel exited: pid: {} stdout: {} stderr: {}'.format(pid, stdout, stderr)
                    logger.info(msg)
                    #c_mqtt.publish(topic, json.dumps({'status': 'INFO', 'message': msg}), mqtt_qos)
                    tunnel_list.append({"pid": pid, "remaining_minutes": remaining_minutes, "status": "exited"})
                    del tunnel_processes[pid]

    except Exception as e:
        msg = 'error checking tunnel processes: {}'.format(e)
        logger.error(msg)
        #c_mqtt.publish(topic, json.dumps({'status': 'ERROR', 'message': msg}), mqtt_qos)
        tunnel_list.append({"status": "error getting tunnel processes"})

    reported_status = {"state": {"reported":{"tunnels": tunnel_list}}}
    c_mqtt.publish(topic, json.dumps(reported_status), mqtt_qos)
    #device_shadow.shadowUpdate(json.dumps(reported_status), shadow_handler_update, 5)
    #Timer(tunnel_processes_monitor_interval, monitor_tunnel_processes).start()


def run_tunnel_manager():
    mqtt_init()
    monitor_tunnel_processes()

    while True:
        Timer(1, monitor_tunnel_processes).start()
        time.sleep(tunnel_processes_monitor_interval)


def stop_tunnel_manager(signum, frame):
    global tunnel_processes

    logger.info('caught signal signum: {}'.format(signum))

    logger.info('disconnecting mqtt clients: {}, {}'.format(client_id, client_id_sdw))
    #c_mqtt.disconnect()
    c_mqtt_sdw.disconnect()

    if tunnel_processes:
        logger.info('killing tunnel processes...')

        for pid in tunnel_processes.keys():
            logger.info('killing process with pid: {}'.format(pid))
            tunnel_processes[pid]['process'].kill()

    logger.info('exiting')
    sys.exit(0)


def main():
    working_directory = os.path.dirname(os.path.realpath(__file__))
    logger.info('daemonizing: working_directory: {} pid_file: {}'.format(working_directory, pid_file))

    ctx = daemon.DaemonContext(
            working_directory=working_directory,
            pidfile=daemon.pidfile.PIDLockFile('{}'.format(pid_file)),
            files_preserve=[fh.stream]
        )

    logger.info('ctx: {}'.format(ctx))

    ctx.signal_map = {
        signal.SIGTERM: stop_tunnel_manager,
        signal.SIGHUP: 'terminate'
    }

    with ctx:
        run_tunnel_manager()

if __name__ == "__main__":
    logger.info('main')
    main()

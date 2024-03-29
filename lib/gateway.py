"""
using adapted library jgillula
  fix powerLevel
  added support for csPin (needs to be set as OUTPUT)
  ack_requested is returned in packet so we can send custom ack info
  support 24bit node id (native attiny device ids)

https://rpi-rfm69.readthedocs.io/en/latest/example_basic.html#better-transceiver
"""

import sys  # noqa: F401
import time  # noqa: F401
from datetime import datetime as dt  # noqa: F401
import threading
from . import Radio, FREQ_868MHZ, FormatDefaults
from .registers import REG_VERSION
from random import randrange
import logging
log = logging.getLogger(__name__)


class Gateway:

    def __init__(self, gateway_id=99, network_id=33,
                 isHighPower=True, verbose=False, interruptPin=18, resetPin=29, autoAcknowledge=False, power=23, dataPacketTypes=None, debugLevel=logging.DEBUG, rssiTarget=-90):

        self.types = dataPacketTypes
        self.formatdefaults = FormatDefaults()  # we use our own "".format() which sets placeholder=0 if not defined

        # needed internally, ensure rssi exists
        self.types["upload"] = self.types.get("upload", {})  # create if not exists
        self.types["upload"]["rssi"] = {
            "type": 0x03,
            "len": 1,
            # sending last_rssi not supported
            "exp": "[(({limit} and 0x01)<<7) | (({reset} and 0x01)<<6) | (({request} and 0x01)<<5) | ({pwrchange}&0x0f)]"
        }
        self.types["download"] = self.types.get("download", {})  # create if not exists
        self.types["download"][0x03] = {
            "name": "rssi",
            "exp": "{{'limit': ({0}&0x80)>>7, 'reset': ({0}&0x40)>>6, 'pwrchange': {0}&0x0f, 'last_rssi': {1}}}"
        }  # 16bit
        self.nodes = {}  # info about the node we communicate with (atc_on_node, atc_on_gw, power_level)

        self.rssi_target = rssiTarget

        self.radio = Radio(FREQ_868MHZ, gateway_id, network_id,
                           isHighPower=isHighPower, verbose=verbose, interruptPin=interruptPin,
                           resetPin=resetPin, autoAcknowledge=autoAcknowledge, power=power)

        log.info("Radio version: 0x{:02X} frq: {} node:0x{:02X}({}) network:{} intPin: {} rstPin: {} csPin: {}, rssiTarget: {}".format(
            self.radio._readReg(REG_VERSION),
            self.radio._freqBand,
            self.radio.address,
            self.radio.address,
            self.radio._networkID,
            self.radio.intPin,
            self.radio.rstPin,
            self.radio.csPin,
            self.rssi_target
        ))

    def __enter__(self):
        self.radio.__enter__()
        return self

    def __exit__(self, *args):
        self.radio.__exit__()

    def listen(self, f_callback):
        # create a thread to run receiveFunction in the background and start it
        receiveThread = threading.Thread(target=self.receiveFunction, args=(f_callback,))
        receiveThread.daemon = True
        receiveThread.start()

        log.info("waiting for data")

    @staticmethod
    def eval_expression(input_string):
        """
        secured eval
        https://realpython.com/python-eval-function/#restricting-globals-and-locals
        """
        allowed_names = {"abs": abs}
        code = compile(input_string, "<string>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                raise NameError(f"Use of {name} not allowed")
        return eval(code, {"__builtins__": {}}, allowed_names)

    @staticmethod
    def get_type_len(byte):
        """ get type and length from first byte of data_packet """
        return (byte >> 4, byte & 0x0f)

    @staticmethod
    def set_type_len(data_type, data_len):
        """ create byte of type and length of data_packet for first byte """
        return ((data_type & 0x0f)) << 4 | (data_len & 0x0f)

    def create_data_packets(self, dict_or_name, value=None):
        if type(dict_or_name) is not dict:
            dict_or_name = {dict_or_name: value}

        data_stream = []
        for type_name, value in dict_or_name.items():
            definition = self.types["upload"][type_name]
            packet_type_len = self.set_type_len(definition["type"], definition["len"])
            if isinstance(value, dict):
                packet_data = self.eval_expression(self.formatdefaults.format(definition["exp"], **value))
            else:
                packet_data = self.eval_expression(self.formatdefaults.format(definition["exp"], value))

            data_stream += [packet_type_len] + packet_data
            #  log.debug("data_stream", [self.to_hex(x) for x in data_stream])
        return data_stream

    def decode_payload(self, payload):
        """
        payload = [0x01, 0xff, 0x14, 0x12, 0x34, 0x56, 0x78]
        """
        # log.debug("payload", ["0x{:02x}".format(x) for x in payload])
        total_len = len(payload)
        i = 0
        data_packets = {}

        while i < total_len:
            data_type, data_len = self.get_type_len(payload[i])
            definition = self.types["download"].get(data_type)
            i += 1  # 1st byte is type/len

            ii = 0
            data = []
            while ii < data_len:
                data.append(payload[i + ii])
                ii += 1

            # check if type defined
            if definition:
                try:
                    data_packets[definition["name"]] = self.eval_expression(definition["exp"].format(*data))
                except:
                    data_packets["unknown"] = data_packets.get("unknown", {})  # create if not exists
                    data_packets["unknown"][data_type] = data
            else:
                data_packets["unknown"] = data_packets.get("unknown", {})  # create if not exists
                data_packets["unknown"][data_type] = data
            # data_packets[types_download[data_type]] = ["0x{:02x}".format(x) for x in data]
            i += ii

        return data_packets

    @staticmethod
    def sign(number):
        return -1 if number < 0 else 1

    @staticmethod
    def to_hex(val, nbits=8):
        return hex((val + (1 << nbits)) % (1 << nbits))

    @staticmethod
    def delFromDict(dictionary, *elements):
        for element in elements:
            if element in dictionary.keys():
                del dictionary[element]

    def get_rssi_correction(self, rssi):
        if not rssi:
            return 0

        """ return 0 if limit reached or no change necessary """
        rssi_diff = self.rssi_target - rssi
        rssi_diff_absolute = abs(rssi_diff)
        rssi_factor = 0
        # rssi_diff_absolute: rssi_factor
        rssi_factors = {14: 7, 7: 4, 4: 2, 2: 1, 0: 0}
        rssi_factor = rssi_factors[list(filter(lambda x: x <= rssi_diff_absolute, rssi_factors))[0]]

        return rssi_factor * self.sign(rssi_diff)

    def receiveFunction(self, f_callback):
        while True:
            # This call will block until a packet is received
            packet = self.radio.get_packet()
            data_packets_received = self.decode_payload(packet.data)
            log.debug("received {} ({}dBm)".format(data_packets_received, packet.RSSI))
            to_upload = {}
            rssi_data_to_upload = {}
            log.debug("  node before: {}".format(self.nodes.get(packet.sender, {})))
            if (packet.ack_requested):
                rssi_dp = data_packets_received.get("rssi", {})
                self.nodes[packet.sender] = self.nodes.get(packet.sender, {})  # ensure self.nodes[nodeId] exists
                if "atc_on_node" not in self.nodes[packet.sender]:
                    self.nodes[packet.sender]["atc_on_node"] = True
                if "atc_on_gw" not in self.nodes[packet.sender]:
                    self.nodes[packet.sender]["atc_on_gw"] = True

                if rssi_dp.get("reset"):
                    self.nodes[packet.sender]["atc_on_node"] = True  # atc running
                    self.nodes[packet.sender]["atc_on_gw"] = True
                    self.delFromDict(self.nodes[packet.sender], "power_level", "random_rssi_request")

                elif rssi_dp.get("limit"):
                    self.nodes[packet.sender]["atc_on_node"] = False  # atc was done at some point

                self.radio.set_power_level(self.nodes[packet.sender].get("power_level", 23))

                # run atc on node (always unless limit reached, whereas node needs to reset to re-start)
                if self.nodes[packet.sender]["atc_on_node"]:
                    power_diff = self.get_rssi_correction(packet.RSSI)
                    if power_diff:
                        rssi_data_to_upload["pwrchange"] = power_diff

                # run atc on gw (only run if we got rssi from node
                last_rssi = -rssi_dp.get("last_rssi", 0)
                if self.nodes[packet.sender]["atc_on_gw"] or last_rssi:
                    if last_rssi:
                        self.delFromDict(self.nodes[packet.sender], "random_rssi_request")

                        rssi_correction = self.get_rssi_correction(last_rssi)
                        log.debug("  gw pwr: {} -> {} ({}dBm)".format(self.radio.powerLevel, rssi_correction, last_rssi))
                        if rssi_correction and self.radio.set_power_level_relative(rssi_correction):
                            rssi_data_to_upload["request"] = 1  # more correction possible, request reception rssi from node
                        else:
                            self.nodes[packet.sender]["atc_on_gw"] = False  # limits reached -> turn atc_on_gw off

                        self.nodes[packet.sender]["power_level"] = self.radio.get_power_level()
                    else:
                        rssi_data_to_upload["request"] = 1  # request reception rssi from node
                # sporadically request rssi to do atc_on_gw
                elif "random_rssi_request" not in self.nodes[packet.sender].keys():
                    rand = randrange(10, 20)
                    self.nodes[packet.sender]["random_rssi_request"] = rand
                elif self.nodes[packet.sender].get("random_rssi_request", 0):
                    self.nodes[packet.sender]["random_rssi_request"] -= 1
                elif self.nodes[packet.sender].get("random_rssi_request", -1) == 0:
                    rssi_data_to_upload["request"] = 1  # request reception rssi from node
                    self.nodes[packet.sender]["random_rssi_request"] = randrange(10, 20)

                if rssi_data_to_upload:
                    to_upload = {"rssi": rssi_data_to_upload}

            # call callback to process data from node
            custom_upload = f_callback(**{
                "data": data_packets_received,
                "upload": to_upload,
                "packet": packet,
            })

            #  if custom_upload is False -> send_ack was processed in callback
            if packet.ack_requested and custom_upload:
                log.debug("  sending {}".format({**to_upload, **custom_upload}))
                #  try seems to be too slow -> more timeouts in node
                """
                stream = []
                for k, v in {**to_upload, **custom_upload}.items():
                    try:
                        stream += self.create_data_packets({k: v})
                    except Exception as e:
                        log.warn("creating data packet {}: {} failed ({})".format(k, v, type(e).__name__))

                self.radio.send_ack(packet.sender, stream)
                """
                try:
                    self.radio.send_ack(packet.sender, self.create_data_packets({**to_upload, **custom_upload}))
                except Exception as e:
                    log.warn("failed to send {}".format(type(e).__name__))

                #  self.radio.send_ack(packet.sender, self.create_data_packets(to_upload))
                #  radio.send_ack(packet.sender, dt.now().strftime("%Y-%m-%d %H:%M:%S"))  # return the current datestamp to the sender

            """
            log.debug(("from 0x{sender:02x} (\033[33;1m{rssi}dBm\033[0m)\n"
                   "  \033[32;1mdbg: {dbg}\033[0m\n"
                   "  \033[32;1mvcc: {vcc}\033[0m\n"
                   "  received raw: {received}\n"
                   "  received: {data}\n"
                   + ("  sent: {sent}" if packet.ack_requested else ""))  # noqa: W503
                  .format(
                      sender=packet.sender,
                      dbg=data_packets_received.get("dbg", "-"),
                      vcc=data_packets_received.get("vcc", "-"),
                      rssi=packet.RSSI,
                      data=data_packets_received,
                      received=[self.to_hex(x) for x in packet.data],
                      sent=to_upload
            ))
            """

    def send(self, target):
        count = 0
        while True:
            count = (count + 1) % 255
            log.debug("sending {} | ".format(count), end="", flush=True)
            self.radio._sendFrame(target, "{}".format(count), 0, 0)
            log.debug("")
            # log.debug("sleep | ", end="", flush=True)
            #  time.sleep(2)
            #  log.debug("retry | ", end="", flush=True)
            #  radio._sendFrame(recipient_id, "}".format(count), 0, 0)
            # log.debug("done")
            # if radio.send(recipient_id, "{}".format(count), attempts=1, waitTime=100):
            #     log.debug("ack")
            # else:
            #     log.debug("no ack")

            time.sleep(2)

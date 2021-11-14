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
import queue
from . import Radio, FREQ_868MHZ
from .registers import REG_VERSION


class Gateway:

    def __init__(self, gateway_id=99, network_id=33,
                 isHighPower=True, verbose=False, interruptPin=18, resetPin=29, autoAcknowledge=False, power=23, dataPacketTypes=None):

        self.types = dataPacketTypes
        # needed internally, ensure rssi exists
        self.types["upload"] = self.types.get("upload", {})  # create if not exists
        self.types["upload"]["rssi"] = {"type": 0x03, "len": 1, "exp": "[{0}&0x0f]"}

        self.rssi_target = -90

        self.radio = Radio(FREQ_868MHZ, gateway_id, network_id,
                           isHighPower=isHighPower, verbose=verbose, interruptPin=interruptPin,
                           resetPin=resetPin, autoAcknowledge=autoAcknowledge, power=power)

        print("Radio version: 0x{:02X} frq: {} node:0x{:02X}({}) network:{} intPin: {} rstPin: {} csPin: {}".format(
            self.radio._readReg(REG_VERSION),
            self.radio._freqBand,
            self.radio.address,
            self.radio.address,
            self.radio._networkID,
            self.radio.intPin,
            self.radio.rstPin,
            self.radio.csPin
        ))

    def __enter__(self):
        self.radio.__enter__()
        return self

    def __exit__(self, *args):
        self.radio.__exit__()

    def listen(self, f_callback):
        q = queue.Queue()
        # create a thread to run receiveFunction in the background and start it
        receiveThread = threading.Thread(target=self.receiveFunction, args=(q,))
        receiveThread.daemon = True
        receiveThread.start()

        print("waiting for data")

        while True:
            data = q.get()
            custom_upload = f_callback(**data) or {}
            if data["ack_requested"]:
                self.radio.send_ack(data["sender"], self.create_data_packets({**data["upload"], **custom_upload}))

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
            first_byte = self.set_type_len(definition["type"], definition["len"])
            data_stream += [first_byte] + self.eval_expression(definition["exp"].format(value))
            #  print("data_stream", [to_hex(x) for x in data_stream])
        return data_stream

    def decode_payload(self, payload):
        """
        payload = [0x01, 0xff, 0x14, 0x12, 0x34, 0x56, 0x78]
        """
        # print("payload", ["0x{:02x}".format(x) for x in payload])
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

            #  TODO catch error if can not decode "exp"
            # check if type defined
            if definition:
                data_packets[definition["name"]] = self.eval_expression(definition["exp"].format(*data))
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

    def receiveFunction(self, queue):
        rssi_atc_on_duty = True
        while True:
            # This call will block until a packet is received
            packet = self.radio.get_packet()
            data_packets_received = self.decode_payload(packet.data)
            to_upload = {}
            if (packet.ack_requested):
                # return possible power change (rssi) if not reached limit
                rss_ctrl = data_packets_received.get("rssi", {})

                if rss_ctrl.get("reset"):
                    rssi_atc_on_duty = True
                elif rssi_atc_on_duty and rss_ctrl.get("limit"):
                    rssi_atc_on_duty = False

                if rssi_atc_on_duty:
                    rssi_diff = self.rssi_target - packet.RSSI
                    rssi_diff_absolute = abs(rssi_diff)
                    rssi_factor = 7 if rssi_diff_absolute > 14 else (4 if rssi_diff_absolute > 7 else 1)
                    rssi_change = rssi_factor * self.sign(rssi_diff) if rssi_diff_absolute > 2 else 0
                    if rssi_change:
                        to_upload = {"rssi": rssi_change}

                #  self.radio.send_ack(packet.sender, self.create_data_packets(to_upload))
                #  radio.send_ack(packet.sender, dt.now().strftime("%Y-%m-%d %H:%M:%S"))  # return the current datestamp to the sender

            queue.put({
                "download": data_packets_received,
                "upload": to_upload,
                "sender": packet.sender,
                "ack_requested": packet.ack_requested,
                "rssi": packet.RSSI
            })
            """
            print(("from 0x{sender:02x} (\033[33;1m{rssi}dBm\033[0m)\n"
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
            print("sending {} | ".format(count), end="", flush=True)
            self.radio._sendFrame(target, "{}".format(count), 0, 0)
            print("")
            # print("sleep | ", end="", flush=True)
            #  time.sleep(2)
            #  print("retry | ", end="", flush=True)
            #  radio._sendFrame(recipient_id, "}".format(count), 0, 0)
            # print("done")
            # if radio.send(recipient_id, "{}".format(count), attempts=1, waitTime=100):
            #     print("ack")
            # else:
            #     print("no ack")

            time.sleep(2)

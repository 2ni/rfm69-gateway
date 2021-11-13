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
from lib import Radio, FREQ_868MHZ
from lib.registers import REG_VERSION

gateway_id = 99
network_id = 33
recipient_id = 0x1E9522

rssi_target = -90

types_download = {
    0x00: {"name": "dbg", "exp": "{0}"},  # 8bit
    0x01: {"name": "vcc", "exp": "{0}<<8 | {1}"},  # 16bit
    0x03: {"name": "rssi", "exp": "{{'limit': ({0}&0x80)>>7, 'reset': ({0}&0x40)>>6, 'pwrchange': {0}&0x0f, 'value': {1}}}"}  # 16bit
}

types_upload = {
    "timestamp": {"type": 0x01, "len": 4, "exp": "[({0} >> i & 0xff) for i in (24, 16, 8, 0)]"},
    "rssi"     : {"type": 0x03, "len": 1, "exp": "[{0}&0x0f]"}  # noqa: E203
}


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


def get_type_len(byte):
    """ get type and length from first byte of data_packet """
    return (byte >> 4, byte & 0x0f)


def set_type_len(data_type, data_len):
    """ create byte of type and length of data_packet for first byte """
    return ((data_type & 0x0f)) << 4 | (data_len & 0x0f)


def create_data_packet(type_name, value):
    first_byte = set_type_len(types_upload[type_name]["type"], types_upload[type_name]["len"])
    data = eval_expression(types_upload[type_name]["exp"].format(value))
    #  print("data", [to_hex(x) for x in data])
    return [first_byte] + data


def decode_payload(stream):
    """
    stream = [0x01, 0xff, 0x14, 0x12, 0x34, 0x56, 0x78]
    """
    # print("stream", stream)
    total_len = len(stream)
    i = 0
    data_packets = {}

    while i < total_len:
        data_type, data_len = get_type_len(stream[i])
        i += 1  # 1st byte is type/len
        ii = 0
        data = []
        while ii < data_len:
            data.append(stream[i + ii])
            ii += 1

        data_packets[types_download[data_type]["name"]] = eval_expression(types_download[data_type]["exp"].format(*data))
        # data_packets[types_download[data_type]] = ["0x{:02x}".format(x) for x in data]
        i += ii

    return data_packets


def sign(number):
    return -1 if number < 0 else 1


def to_hex(val, nbits=8):
    return hex((val + (1 << nbits)) % (1 << nbits))


def receiveFunction(radio):
    rssi_atc_on_duty = True
    while True:
        # This call will block until a packet is received
        packet = radio.get_packet()
        ack_sent = False
        if (packet.ack_requested):
            data_packets_received = decode_payload(packet.data)
            data_packets_to_send = []
            # return possible power change (rssi) if not reached limit
            rss_ctrl = data_packets_received.get("rssi", {})

            if rss_ctrl.get("reset"):
                rssi_atc_on_duty = True
            elif rssi_atc_on_duty and rss_ctrl.get("limit"):
                rssi_atc_on_duty = False

            if rssi_atc_on_duty:
                rssi_diff = rssi_target - packet.RSSI
                rssi_change = sign(rssi_diff) if abs(rssi_diff) > 3 else 0
                if rssi_change:
                    data_packets_to_send += create_data_packet("rssi", rssi_change)

            # return timestamp in seconds (uint32_t)
            now = int(time.time())
            data_packets_to_send += create_data_packet("timestamp", now)

            radio.send_ack(packet.sender, data_packets_to_send)
            #  radio.send_ack(packet.sender, dt.now().strftime("%Y-%m-%d %H:%M:%S"))  # return the current datestamp to the sender
            ack_sent = True

        print(("from 0x{sender:02x} (\033[33;1m{rssi}dBm\033[0m)\n"
               "  \033[32;1mdbg: {dbg}\033[0m\n"
               "  \033[32;1mvcc: {vcc}\033[0m\n"
               "  received raw: {received}\n"
               "  received: {data}\n"
               + ("  ack sent: {ack}\n  sent: {sent}" if ack_sent else ""))  # noqa: W503
              .format(
                  sender=packet.sender,
                  dbg=data_packets_received.get("dbg", "-"),
                  vcc=data_packets_received.get("vcc", "-"),
                  rssi=packet.RSSI,
                  ack=now,
                  data=data_packets_received,
                  received=[to_hex(x) for x in packet.data],
                  sent=[to_hex(x) for x in data_packets_to_send]
        ))


try:
    with Radio(FREQ_868MHZ, gateway_id, network_id,
               isHighPower=True, verbose=False, interruptPin=18, resetPin=29, autoAcknowledge=False, power=23) as radio:

        print("Radio version: 0x{:02X} frq: {} node:0x{:02X}({}) network:{} intPin: {} rstPin: {} csPin: {}".format(
            radio._readReg(REG_VERSION),
            radio._freqBand,
            radio.address,
            radio.address,
            radio._networkID,
            radio.intPin,
            radio.rstPin,
            radio.csPin
        ))

        # Create a thread to run receiveFunction in the background and start it
        receiveThread = threading.Thread(target=receiveFunction, args=(radio,))
        receiveThread.daemon = True
        receiveThread.start()

        print("waiting for data")
        while True:
            pass

        """
        count = 0
        while True:
            count = (count + 1) % 255
            print("sending {} | ".format(count), end="", flush=True)
            radio._sendFrame(recipient_id, "{}".format(count), 0, 0)
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
        """

except KeyboardInterrupt:
    print("done.")

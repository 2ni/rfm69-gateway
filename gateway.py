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


def eval_expression(input_string):
    """
    secured eval
    https://realpython.com/python-eval-function/#restricting-globals-and-locals
    """
    allowed_names = {}
    code = compile(input_string, "<string>", "eval")
    for name in code.co_names:
        if name not in allowed_names:
            raise NameError(f"Use of {name} not allowed")
    return eval(code, {"__builtins__": {}}, allowed_names)


def decodeStream(stream):
    """
    stream = [0x01, 0xff, 0x14, 0x12, 0x34, 0x56, 0x78]
    """
    # print("stream", stream)
    total_len = len(stream)
    i = 0
    data_packets = {}
    types = {
        0x00: {"name": "dbg",       "exp": "{0}"},                               # noqa: E241 8bit
        0x01: {"name": "timestamp", "exp": "{0}<<24 | {1}<<16 | {2}<<7 | {3}"},  # 32bit
        0x08: {"name": "vcc",       "exp": "{0}<<8 | {1}"}                       # noqa: E241 16bit
    }

    while i < total_len:
        first_byte = stream[i]
        data_type, data_len = (first_byte >> 4, first_byte & 0x0f)
        i += 1  # 1st byte is type/len
        ii = 0
        data = []
        while ii < data_len:
            data.append(stream[i + ii])
            ii += 1

        data_packets[types[data_type]["name"]] = eval_expression(types[data_type]["exp"].format(*data))
        # data_packets[types[data_type]] = ["0x{:02x}".format(x) for x in data]
        i += ii

    return data_packets


def receiveFunction(radio):
    while True:
        # This call will block until a packet is received
        packet = radio.get_packet()
        ack_sent = False
        if (packet.ack_requested):
            # send current timestamp in seconds (uint32_t)
            # [type|len](1) [ts](4)
            now = int(time.time())
            radio.send_ack(packet.sender, [0x01 << 4 | 0x04] + [(now >> i & 0xff) for i in (24, 16, 8, 0)])
            #  radio.send_ack(packet.sender, dt.now().strftime("%Y-%m-%d %H:%M:%S"))  # return the current datestamp to the sender
            ack_sent = True

        decoded = decodeStream(packet.data)
        print("from 0x{sender:02x} ({rssi}dBm)\n  \033[32;1mdbg: {dbg}\033[0m\n  \033[32;1mvcc: {vcc}\033[0m\n  ack sent: {ack}\n  data: {data}\n  raw: {raw}".format(
            sender=packet.sender,
            dbg=decoded.get("dbg", "-"),
            vcc=decoded.get("vcc", "-"),
            rssi=packet.RSSI,
            ack=now if ack_sent else False,
            data=decoded,
            raw=["0x{:02x}".format(x) for x in packet.data]
        ))
        #  print("from 0x{:02X}: \"{}\" ({}dBm)".format(packet.sender, packet.data_string, packet.RSSI))
        #  print("from %s: \"%s\" (%sdBm)" % (packet.sender, packet.data_string, packet.RSSI))


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

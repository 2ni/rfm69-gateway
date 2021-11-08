"""
using adapted library jgillula
  fix powerLevel
  added support for csPin (needs to be set as OUTPUT)
  ack_requested is returned in packet so we can send custom ack info
  support 24bit node id (native attiny device ids)

https://rpi-rfm69.readthedocs.io/en/latest/example_basic.html#better-transceiver
"""

import time  # noqa: F401
from datetime import datetime as dt  # noqa: F401
import threading
from lib import Radio, FREQ_868MHZ
from lib.registers import REG_VERSION

gateway_id = 99
network_id = 33
recipient_id = 0x1E9522


def receiveFunction(radio):
    while True:
        # This call will block until a packet is received
        packet = radio.get_packet()
        if (packet.ack_requested):
            # send current timestamp in seconds (uint32_t)
            #  now = int(time.time())
            #  radio.send_ack(packet.sender, [(now >> i & 0xff) for i in (24, 16, 8, 0)])
            radio.send_ack(packet.sender, dt.now().strftime("%Y-%m-%d %H:%M:%S"))  # return the current datestamp to the sender
            print("ack | ", end="")

        print("from 0x{:02X}: \"{}\" ({}dBm)".format(packet.sender, packet.data_string, packet.RSSI))
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

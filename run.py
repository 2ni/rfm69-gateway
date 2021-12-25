import threading
import time
import logging
import argparse
from lib import Gateway

log = logging.getLogger(__name__)

dataPacketTypes = {
    "download": {
        0x00: {"name": "dbg", "exp": "{0}"},  # 1byte
        0x01: {"name": "vcc", "exp": "{0}<<8 | {1}"},  # 2bytes
        0x08: {"name": "humidity", "exp": "{0}"},  # 1byte
        0x09: {"name": "temperature", "exp": "{0}<<8 | {1}"}  # 2bytes
    },
    "upload": {
        "timestamp": {"type": 0x01, "len": 4, "exp": "[({0} >> i & 0xff) for i in (24, 16, 8, 0)]"},
    }
}


def colorize(color, str):
    colors = {"red": "31", "green": "32", "yellow": "33"}
    color_code = colors.get(color)

    if color_code:
        return "\033[{};1m{}\033[0m".format(color_code, str)
    else:
        return str


def process_data(data, packet, upload):
    # to see if node asked for a reset -> check data["rssi"]["reset"]
    print("  {} from 0x{:06x} ({}dBm)".format(colorize("green", data), packet.sender, packet.RSSI), flush=True)


def callback(data, upload, packet):
    """
    @return dict with data to upload. Return false if send_ack processed in this function
    data: decoded data received from the node
        data["unknown"] contains data not configured in dataPacketTypes
    upload: potential system upload data which will be sent to gw (don't touch)
    packet:
        packet.sender         ID from sender node
        packet.ack_requested  if node requested an ack
        packet.RSSI           RSSI of data reception
        packet.payload        raw data received from the node
    """

    # do some stuff with data from node
    # should not block and be fast, that's why we use threads
    thread = threading.Thread(target=process_data, args=(data, packet, upload))
    thread.start()

    # send data back to node with ack
    # eg timestamp in seconds (uint32_t)
    now = int(time.time())
    to_upload = {"timestamp": now}

    return to_upload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="run rfm69 gateway", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-l', '--level', type=str, default="warn", choices=["debug", "info", "warn", "error", "critical"], help="Logging level")
    args = parser.parse_args()
    level = logging.getLevelName(args.level.upper())
    logging.basicConfig(format="%(asctime)s: %(message)s", datefmt='%Y-%m-%d %H:%M:%S', level=level)
    try:
        with Gateway(dataPacketTypes=dataPacketTypes, debugLevel=level) as gateway:
            gateway.listen(callback)

            while True:
                pass
    except KeyboardInterrupt:
        log.info("Done.")

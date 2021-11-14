import sys  # noqa: F401
import time  # noqa: F401
from datetime import datetime as dt  # noqa: F401
from lib import Gateway

dataPacketTypes = {
    "download": {
        0x00: {"name": "dbg", "exp": "{0}"},  # 8bit
        0x01: {"name": "vcc", "exp": "{0}<<8 | {1}"},  # 16bit
        0x03: {"name": "rssi", "exp": "{{'limit': ({0}&0x80)>>7, 'reset': ({0}&0x40)>>6, 'pwrchange': {0}&0x0f, 'value': {1}}}"}  # 16bit
    },
    "upload": {
        "timestamp": {"type": 0x01, "len": 4, "exp": "[({0} >> i & 0xff) for i in (24, 16, 8, 0)]"},
    }
}


def callback(download, upload, sender, ack_requested, rssi):
    # send timestamp in seconds (uint32_t)
    now = int(time.time())
    to_upload = {"timestamp": now}

    print("{} from 0x{:06x} ({}dBm)".format(download, sender, rssi), flush=True)
    return to_upload


if __name__ == "__main__":
    try:
        with Gateway(dataPacketTypes=dataPacketTypes) as gateway:
            gateway.listen(callback)

            while True:
                pass
    except KeyboardInterrupt:
        print("Done.")

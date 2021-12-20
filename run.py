import time
from lib import Gateway

dataPacketTypes = {
    "download": {
        0x00: {"name": "dbg", "exp": "{0}"},  # 8bit
        0x01: {"name": "vcc", "exp": "{0}<<8 | {1}"},  # 16bit
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


def callback(gateway, download, upload, sender, ack_requested, rssi):
    """
    @return dict with data to upload. Return false if send_ack processed in this function
    download: data from node
        download["unknown"] contains data not configured in dataPacketTypes
    upload: potential system upload data which will be sent to gw (don't touch)
    sender: ID from node
    ack_requested: if node requested an ack
    rssi: RSSI of data receiption
    gateway: can be used to send the ack in this code to not block the ack response, eg:
        if ack_requested:
            now = int(time.time())
            gateway.radio.send_ack(sender, self.create_data_packets({**upload, **{"timestamp": now}}))

        # do stuff with the data after sending ack
    """

    # do some stuff with data from node
    # should not block and be fast, best async

    print("  {} from 0x{:06x} ({}dBm)".format(colorize("green", download), sender, rssi), flush=True)

    # send data back to node with ack
    # eg timestamp in seconds (uint32_t)
    now = int(time.time())
    to_upload = {"timestamp": now}

    return to_upload


if __name__ == "__main__":
    try:
        with Gateway(dataPacketTypes=dataPacketTypes) as gateway:
            gateway.listen(callback)

            while True:
                pass
    except KeyboardInterrupt:
        print("Done.")

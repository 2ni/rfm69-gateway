### Description
- RFM69 gateway in python based on [jgillula](https://github.com/jgillula/rpi-rfm69)'s implementation.
- runs on raspberry pi 4
- fixes some powerLevel issues on HCW
- adds support for csPin (needs to be set as OUTPUT)
- ack_requested is returned in a packet so we can send custom ack with data
- support 24bit node ids (native attiny device ids)
- see also my attiny3217 [node](https://github.com/2ni/apricot/tree/main/examples/rfm69)

### Installation
```
sudo apt install python3-venv python3-rpi.gpio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Debugging SPI
[test](https://www.raspberrypi.org/documentation/hardware/raspberrypi/spi/README.md) if SPI is working:

### Reload SPI
```
raspi-config              # enable spi on interface options
lsmod | grep spi          # check if spi enabled and to get spi module name, eg spi_bcm2835
sudo rmmod spi_bcm2835    # remove it
sudo modprobe spi_bcm2835 # readd it

sudo dtparam spi=on       # or off to enable/disable spi
```

## Lowlevel testing

```
ll /dev/spidev0.*
wget https://raw.githubusercontent.com/raspberrypi/linux/rpi-3.10.y/Documentation/spi/spidev_test.c
gcc -o spidev_test spidev_test.c
./spidev_test -D /dev/spidev0.0
spi mode: 0
bits per word: 8
max speed: 500000 Hz (500 KHz)

FF FF FF FF FF FF
40 00 00 00 00 95
FF FF FF FF FF FF
FF FF FF FF FF FF
FF FF FF FF FF FF
DE AD BE EF BA AD
F0 0D
```

## Loopback test

Connect MISO with MOSI and run:
```
python test/loopback.py
0x01 0x02
0x01 0x02
...
```

## Test "get current version"

Connect your RFM69 as described in the [library](https://github.com/2ni/RFM69):

| RFM pin | Pi pin
| ------- |-------
| 3v3     | 17
| DIO0    | 18
| MOSI    | 19
| MISO    | 21
| CLK     | 23
| NSS     | 24
| Ground  | 25
| RESET   | 29

```
python test/version.py
all good! Version: 0x24
all good! Version: 0x24
all good! Version: 0x24
...
```

## Run gateway
```
python gateway.py
```

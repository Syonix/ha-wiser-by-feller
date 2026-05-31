"""Mock a zeroconf device.

Due to networking limitations in docker, zeroconf device discovery is hard to test in the devcontainer.
Run this script instead to fake-register a device. It should be autodiscovered by Home Assistant as long as the script is running.

Usage:
$ python3 scripts/mock-zeroconf.py 192.168.0.99
"""

import socket
import sys

from zeroconf import ServiceInfo, Zeroconf

if len(sys.argv) < 2:
    print("Usage: python3 scripts/mock-zeroconf.py <ip-address>")
    sys.exit(1)

print(f"Broadcasting device with IP {sys.argv[1]}")

info = ServiceInfo(
    type_="_http._tcp.local.",
    name="wiser-00123456._http._tcp.local.",
    addresses=[socket.inet_aton(sys.argv[1])],
    port=80,
)

zeroconf = Zeroconf()
zeroconf.register_service(info)

input("Press Enter to exit and unregister...")
zeroconf.unregister_service(info)
zeroconf.close()

# Mission Control

A [Sessen](https://github.com/ElizabethF2/Sessen) extension that enables applications to be proxied and jobs to be launched via a hosted message bus service as a means of NAT traversal.

This repo is also the home of the Mission Control Bus which is used as a relay by both [Mission Control Lite](https://github.com/ElizabethF2/MissionControlLite) and [CharonRMM](https://github.com/ElizabethF2/CharonRMM).

## Setup

Generate a certificate for the bus using the command below, substituting your desired expiration date for `99999` and the actual domain name for `example.org`:

```
openssl req -x509 -out cert.pem -keyout key.pem -newkey rsa:2048 -nodes -sha256 -days 99999 -subj '/CN=MCBUS' -addext 'subjectAltName = DNS:example.org'
```

Copy `cert.pem`, `key.pem` and `message_bus.py` to the server you'll be using to host the bus. Use a service file, cron job, procfile, your host's control panel or any other method of your choosing to configure the command `python message_bus.py` to be run at boot or whenever a request to the bus is received.

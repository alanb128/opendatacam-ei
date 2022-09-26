#!/bin/sh

# Here we download the latest model each time the container starts

# EI_API_KEY defined as environment variables in BalenaCloud
edge-impulse-linux-runner --api-key $EI_API_KEY --download modelfile.eim

# Give the downloader some breathing time
sleep 10

# To start our Python script that pulls data from Opendatacam,
#   runs inferences, and optionally sends training files back to EI cloud,
#   uncomment the line below and comment the sleep line.
# python3 runner.py

sleep infinity

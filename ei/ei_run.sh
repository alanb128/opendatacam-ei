#!/bin/sh

# Here we download the latest model each time the container starts

# EI_API_KEY defined as environment variables in BalenaCloud
edge-impulse-linux-runner --api-key $EI_API_KEY --download modelfile.eim

# Give the downloader some breathing time
sleep 10

# Start our Python script that pulls data from Opendatacam,
#   runs inferences, and optionally sends training files back to EI cloud
python3 runner.py

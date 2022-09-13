#!/bin/sh
# EI_API_KEY defined as environment variables in BalenaCloud

# Fill out and uncomment for local deployment
#EI_API_KEY=""
#EI_COLLECT_MODE=0

if [ $EI_COLLECT_MODE = "1" ];
then
    edge-impulse-linux --api-key $EI_API_KEY --disable-microphone
else
    edge-impulse-linux-runner --api-key $EI_API_KEY --download modelfile.eim
fi


#sleep 5

#while [[ true ]]; do
#    echo "Checking internet connectivity ..."
#    wget --spider --no-check-certificate 1.1.1.1 > /dev/null 2>&1
#
#    if [ $? -eq 0 ]; then
#        echo "Your device is connected to the internet."
#        
#    else
#        echo "Your device is not connected to the internet."
#        
#    fi
#
#    sleep $freq
#
#done
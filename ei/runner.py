import requests
import json
import datetime
import time, hmac, hashlib
import csv
import os
import sys, getopt
import signal
from edge_impulse_linux.runner import ImpulseRunner
import io
import re, uuid
import math

# Can be set by device variables or will use default
save_data_files = True
if os.getenv('SAVE_DATA_FILES', '1') != '1':
    save_data_files = False
upload_data_files = False
if os.getenv('UPLOAD_DATA_FILES', '0') == '1':
    upload_data_files = True
inference_on = True
if os.getenv('INFERENCE_ON', '1') != '1':
    inference_on = False
demo_mode = False
if os.getenv('DEMO_MODE', '0') == '1':
    demo_mode = True
else:
    demo_mode = False
hmac_key = os.getenv('HMAC_KEY')
api_key = os.getenv('API_KEY')
line_left_name = os.getenv('LINE_LEFT_NAME', 'line_left')
line_right_name = os.getenv('LINE_RIGHT_NAME', 'line_right')
line_left = ''
line_right = ''
sample_interval = int(os.getenv('SAMPLE_INTERVAL', '60'))  # seconds

# Data for demo mode
demo_data = [[2, 1310], [4, 1000], [7, 1123], [5, 888], [1, 2233], [2, 2133], [1, 1343], [2, 919]]
demo_index = 0  # last demo index used

# Initialize global variables
recording_count = 1
fieldnames = ['car_count', 'avg_speed']
final = []
classification = "unknown"  # Most recent onboard classification by EI model
feature = ""  # Most recent feature from sample

# FOR TESTING ONLY!!!!
#sample_interval = 45
#upload_data_files = True
#demo_mode = True
#line_left = '583e3f17-56de-4926-ab74-22fc4eb6afe8' # line_left
#line_right = '6841ecc6-ccdd-4988-b913-159aab85ab28'
#line_left_name = "line_south"
#line_right_name = "line_north"

def get_traffic(total_cars):

    #
    # Categorizes traffic levels based on car count
    #

    if total_cars < 6:
        return "light"
    if total_cars < 13:
        return "moderate"
    else:
        return "heavy"

def get_last_recording():

    #
    # return id of last recording
    #
    r = requests.get("http://opendatacam:8080/recordings?limit=1")
    recording_id = 0
    recordings = r.json()
    for recording in recordings['recordings']:
        recording_id = recording['_id']

    #print("Last recording is: {}.".format(recording_id))
    return recording_id

def save_rec_data(recording_id):

    #
    # Pulls recording data and saves to file for inference and/or training
    #
    global feature
    cars = []
    car_count = 0
    total_car_count = 0

    r = requests.get("http://opendatacam:8080/recording/" + recording_id + "/counter")
    rec_counter = r.json()
    updated = False
    rec_date = datetime.datetime.strptime(rec_counter['dateStart'], '%Y-%m-%dT%H:%M:%S.%fZ')
    # Test for existence of counter history
    # if error, no cars recorded, return non-zero error for function
    try:
        b = rec_counter['counterHistory']
    except:
        print("No cars tracked in this data sample!")
        return 99
    # for each counted item...
    for h in rec_counter['counterHistory']:
        if h['name'] == "car":
            # loop through our list to see if car exists in our car list
            car_count = 0
            for car in cars:
                updated = False
                if car["id"] == h["id"]:
                    # car is already in list, so update dict for car in list
                    updated = True
                    if h['area'] == line_left:
                        cars[car_count]['left_time'] = h['timestamp']
                    else:
                        cars[car_count]['right_time'] = h['timestamp']
                car_count = car_count + 1

            if not updated:
                # car does not exist, append it to our car list
                # this creates a dict in the car list
                if h['area'] == line_left:
                    cars.append({'id': h['id'], 'left_time': h['timestamp'], 'right_time': "0:00"})
                else:
                    cars.append({'id': h['id'], 'left_time': "0:00", 'right_time': h['timestamp']})
                # update newly added car with any sensor/constant data here

    # Now we have a list of dicts
    # calculate journey time for cars that have crossed both lines

    car_count = 0
    for car in cars:
        if car['left_time'] != "0:00" and car['right_time'] != "0:00":
            # car has crossed both lines
            car_count = car_count + 1
            left_time = datetime.datetime.strptime(car['left_time'], '%Y-%m-%dT%H:%M:%S.%fZ')
            right_time = datetime.datetime.strptime(car['right_time'], '%Y-%m-%dT%H:%M:%S.%fZ')
            diff = left_time - right_time
            elapsed = diff.total_seconds() * 1000  # milliseconds for car to go from one line to the other
            ts_diff = right_time - rec_date
            timestamp = ts_diff.total_seconds() * 1000  # milliseconds from recording start to crossing first line
            car.update({'timestamp': timestamp})
            car.update({'duration': elapsed})
            car.update({'hod': rec_date.hour})  # hour of day
        else:
            # car has not crossed both lines
            car.update({'duration': 0})
    total_car_count = car_count

    final = []  # list holding final data for each car that crossed both lines
    # For cars where duration > 0, save data
    car_count = 0
    for car in cars:
        if car['duration'] != 0:
            # car has crossed both lines
            car_count = car_count + 1
            # add dict to final list
            final.append({'timestamp': int(car['timestamp']), 'journey_dur': int(car['duration']), 'hod': car['hod']})
    print("Found {} car journey(s).".format(car_count))

    if car_count > 0:
        # Summarize the final list
        journey_sum = 0
        hod = 0
        for item in final:
            journey_sum = journey_sum + int(item['journey_dur'])
            hod = item['hod']  # will only get last value in final
        final_mod = [car_count, journey_sum/car_count]
        print("Final sample data: {}".format(final_mod))
        if save_data_files:
            nf = "{:02d}{:02d}{:02d}{:02d}{:02d}".format(rec_date.month, rec_date.day, rec_date.hour, rec_date.minute, rec_date.second)
            feature = get_traffic(total_car_count)
            fname = feature + ".sample" + nf + ".csv"
            with open(fname, "w", encoding="UTF8", newline="") as csvs:
                writer = csv.writer(csvs)
                writer.writerow(fieldnames)
                writer.writerow(final_mod)
            csvs.close()
            print("SAVE_DATA_FILES=True; Saved to file: {}".format(fname))
            #
            # Alternate way of saving data files below
            # This provides one car per row with timestamp
            #if car_count == 0:
            #    print("NOTE: No cars detected, using default values!")
            #    final.append({'timestamp': 1000, 'journey_dur': 1000, 'hod': 0} )
            #with open(fname, "w", encoding="UTF8", newline="") as csvf:
            #    writer = csv.DictWriter(csvf, fieldnames=fieldnames)
            #    writer.writeheader()
            #    writer.writerows(final)
            #print("SAVED_DATA_FILE=True; Saved to file: {}".format(fname))
            #

        # Always save to features.txt if needed for inferencing or uploading

        with open("features.txt", "w", encoding="UTF8", newline="") as csvf:
            writer = csv.writer(csvf)
            # no header
            writer.writerow(final_mod)
        csvf.close()
        #print("Saved features.txt")
    else:
        print("No files saved...")
        return 99

    return 0

def value_getter(item):
    #
    # Used by EI_inference() for sorting
    #
    return item[1]

def EI_inference():
    #
    # Uses local model file to perform inference on collected data
    #

    global classification
    print("     ")
    print("Starting local EI inference on model...")

    runner = None

    features_file = io.open("/usr/src/app/features.txt", 'r', encoding='utf8')
    features = features_file.read().strip().split(",")
    if '0x' in features[0]:
        features = [float(int(f, 16)) for f in features]
    else:
        features = [float(f) for f in features]

    dir_path = os.path.dirname(os.path.realpath(__file__))
    modelfile = "/usr/src/app/modelfile.eim"

    runner = ImpulseRunner(modelfile)
    try:
        model_info = runner.init()
        print('Loaded runner for "' + model_info['project']['owner'] + ' / ' + model_info['project']['name'] + '"')

        res = runner.classify(features)
        #print("res: {}".format(res))
        result = res['result']['classification']
        sort = sorted(result.items(), key=value_getter)
        #print("sorted: {}".format(sort))
        print("^^^^ Local classification results: ^^^^")
        for s in sort:
            print("{}: {}%".format(s[0], int(s[1] * 100)))
            classification = s[0]  # Should give us the last (highest) one!
        #print("classification:")
        #print(res["result"])
        print("Timing information: {}".format(res["timing"]))

    finally:
        if (runner):
            runner.stop()

def EI_collect():
    #
    # Send collected sample back to EI for re-training
    # https://github.com/edgeimpulse/linux-sdk-python/blob/master/examples/custom/collect.py
    #
    print("      ")
    print("Preparing to upload data file to Edge Impulse")
    # empty signature (all zeros). HS256 gives 32 byte signature, and we encode in hex, so we need 64 characters here
    emptySignature = ''.join(['0'] * 64)

    # use MAC address of network interface as deviceId
    device_name =":".join(re.findall('..', '%012x' % uuid.getnode()))

    # here we have new data every 60,000 ms
    INTERVAL_MS = 1000  # was 60000

    # pull the values from the features.txt file
    values_list=[]
    with open('features.txt') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            #print("row 0:{}".format(row[0]))
            #print("row 1:{}".format(row[1]))
            values_list.append([int(row[0]), int(float(row[1])), 19])
            #values_list.append([5,2323,19])
    data = {
        "protected": {
            "ver": "v1",
            "alg": "HS256",
            "iat": time.time() # epoch time, seconds since 1970
        },
        "signature": emptySignature,
        "payload": {
            "device_name":  device_name,
            "device_type": "LINUX_TEST",
            "interval_ms": INTERVAL_MS,
            "sensors": [
                { "name": "car_count", "units": "units" },
                { "name": "avg_speed", "units": "ms" }
            ],
            "values": values_list
        }
    }

    # encode in JSON
    encoded = json.dumps(data)

    # sign message
    signature = hmac.new(bytes(hmac_key, 'utf-8'), msg = encoded.encode('utf-8'), digestmod = hashlib.sha256).hexdigest()

    # set the signature again in the message, and encode again
    data['signature'] = signature
    encoded = json.dumps(data)

    # Get user input for label
    my_input = input("Type a label or enter for [{}]\n".format(classification)) or classification

    # and upload the file
    res = requests.post(url='https://ingestion.edgeimpulse.com/api/training/data',
                    data=encoded,
                    headers={
                        'Content-Type': 'application/json',
                        'x-file-name': my_input,
                        'x-api-key': api_key
                    })
    if (res.status_code == 200):
        print('Uploaded file to Edge Impulse', res.status_code, res.content)
    else:
        print('Failed to upload file to Edge Impulse', res.status_code, res.content)

def get_demo_data(rec_filename):
    #
    # Copies included demo files to look real
    #
    global demo_index

    demo_index = demo_index + 1
    if demo_index > len(demo_data):
        demo_index = 0
    
    final_mod = demo_data[demo_index]
    print("Final demo sample data: {}".format(final_mod))
    rec_date = datetime.datetime.now()
    if save_data_files:
        nf = "{:02d}{:02d}{:02d}{:02d}{:02d}".format(rec_date.month, rec_date.day, rec_date.hour, rec_date.minute, rec_date.second)
        feature = get_traffic(final_mod[0])
        fname = feature + ".sample" + nf + ".csv"
        with open(fname, "w", encoding="UTF8", newline="") as csvs:
            writer = csv.writer(csvs)
            writer.writerow(fieldnames)
            writer.writerow(final_mod)
        csvs.close()
        print("SAVE_DATA_FILES=True; Saved to file: {}".format(fname))

    with open("features.txt", "w", encoding="UTF8", newline="") as csvf:
        writer = csv.writer(csvf)
        #writer.writeheader()
        writer.writerow(final_mod)
    print("Saved features.txt")
    csvf.close()

    return 0

def get_odc_lines():
    #
    # Gets the counting lines from Opendatacam
    #
    global line_left, line_right
    r = requests.get("http://opendatacam:8080/counter/areas")
    areas = r.json()
    for area in areas:
        if areas[area]['name'] == line_left_name:
            line_left = area
        else:
            line_right = area
    if line_left == '' or line_right == '':
        return 99
    else:
        print("Found areas:")
        print("{}: {}".format(line_left_name, line_left))
        print("{}: {}".format(line_right_name, line_right))
        return 0

# Start here

print("####################################################")
print("     ")
if demo_mode:
    print("Starting runner in DEMO mode...")
else:
    print("Starting runner!")
if get_odc_lines() != 0:
    print("Incorrect or no counting lines in Opendatacam. Please fix and then re-run.")
    sys.exit(0)
while True:
    print("     ")
    print("####################################################")
    print("     ")
    if demo_mode:
        print("Started mock recording #{} for next {} second(s)...".format(recording_count, sample_interval))
    else:
        r = requests.get("http://opendatacam:8080/recording/start")
        print("Started recording #{} for next {} second(s)...".format(recording_count, sample_interval))
        print("Response from odc: {}".format(r.text))

    started = datetime.datetime.now()
    started_formatted = "{:02d}{:02d}{:02d}{:02d}{:02d}".format(started.month, started.day, started.hour, started.minute, started.second)
    #print("Started recording file: {}.".format(started_formatted))

    interval_qtr = sample_interval/4
    time.sleep(interval_qtr)
    print("{} s. remaining...".format(interval_qtr * 3))
    time.sleep(interval_qtr)
    print("{} s. remaining...".format(interval_qtr * 2))
    time.sleep(interval_qtr)
    print("{} s. remaining...".format(interval_qtr))
    time.sleep(interval_qtr)
    print("Stopping recording...")
    ret = 0
    if demo_mode:
        ret = get_demo_data(started_formatted)
    else:
        r = requests.get("http://opendatacam:8080/recording/stop")
        rr = get_last_recording()
        ret = save_rec_data(rr)

    if ret == 0:
        if inference_on:
            # Call EI inference code here
            EI_inference()

        if upload_data_files:
            # Upload files back to EI for training
            EI_collect()

    else:
        print("No cars detected, skipping inference/upload and moving to next recording.")
        print("     ")

    recording_count = recording_count + 1

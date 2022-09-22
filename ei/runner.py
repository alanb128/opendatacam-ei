import requests
import json
import datetime
import time
import csv
import os
import sys, getopt
import signal
from edge_impulse_linux.runner import ImpulseRunner
import io

# Can be set by device variables or will use default
if os.getenv('SAVE_DATA_FILES', '1') != '1':
    save_data_files = False
else:
    save_data_files = True
if os.getenv('UPLOAD_DATA_FILES', '0') != '1':
    upload_data_files = True
else:
    upload_data_files = False
if os.getenv('INFERENCE_ON', '1') != '1':
    inference_on = False
else:
    inference_on = True
line_left = os.getenv('LINE_LEFT_ID', '583e3f17-56de-4926-ab74-22fc4eb6afe8') # line_left
line_right = os.getenv('LINE_RIGHT_ID', '6841ecc6-ccdd-4988-b913-159aab85ab28') # line_right
sample_interval = int(os.getenv('SAMPLE_INTERVAL', '40'))  # seconds

# Initialize global variables
recording_count = 1
fieldnames = ['timestamp', 'journey_dur', 'hod']
final = []

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

    print("Last recording is: {}.".format(recording_id))
    return recording_id

def save_rec_data(recording_id):

    #
    # Pulls recording data and saves to file for inference or training
    #
    cars = []
    #journey = {"id": 0, "left_time": "2022-09-14T22:59:07.479Z", "right_time": "2022-09-14T22:59:07.479Z"}
    car_count = 0
    total_car_count = 0

    r = requests.get("http://opendatacam:8080/recording/" + recording_id + "/counter")
    rec_counter = r.json()
    updated = False
    rec_date = datetime.datetime.strptime(rec_counter['dateStart'], '%Y-%m-%dT%H:%M:%S.%fZ')
    # for each counted item...
    for h in rec_counter['counterHistory']:
        if h['name'] == "car":
            # loop through our list to see if car exists
            car_count = 0
            for car in cars:
                updated = False
                if car["id"] == h["id"]:
                    # car is already in list, so update
                    updated = True
                    if h['area'] == line_left:
                        cars[car_count]['left_time'] = h['timestamp']
                        #cars[car_count]['right_time'] = "0:00"
                    else:
                        #cars[car_count]['left_time'] = "0:00"
                        cars[car_count]['right_time'] = h['timestamp']
                car_count = car_count + 1

            if not updated:
                # car does not exist, append it
                if h['area'] == line_left:
                    cars.append({'id': h['id'], 'left_time': h['timestamp'], 'right_time': "0:00"})
                else:
                    cars.append({'id': h['id'], 'left_time': "0:00", 'right_time': h['timestamp']})
                # update newly added car with any sensor/constant data here
                

    # Now we have a list of dicts
    # calculate journey time for cars that have crossed both lines
    #print(cars)

    car_count = 0
    for car in cars:
        if car['left_time'] != "0:00" and car['right_time'] != "0:00":
            car_count = car_count + 1
            left_time = datetime.datetime.strptime(car['left_time'], '%Y-%m-%dT%H:%M:%S.%fZ')
            right_time = datetime.datetime.strptime(car['right_time'], '%Y-%m-%dT%H:%M:%S.%fZ')
            diff = left_time - right_time
            elapsed = diff.total_seconds() * 1000  # milliseconds
            #print("here 2")
            ts_diff = right_time - rec_date
            timestamp = ts_diff.total_seconds() * 1000
            car.update({'timestamp': timestamp})
            car.update({'duration': elapsed})
            car.update({'hod': left_time.hour})  # hour of day
        else:
            #cars.remove(car)
            car.update({'duration': 0})
    total_car_count = car_count

    #print("--  ")
    #print(cars)
    final = []
    # For cars where duration > 0, save data
    car_count = 0
    for car in cars:
        if car['duration'] != 0:
            car_count = car_count + 1
            #print("here 3")
            final.append({'timestamp': int(car['timestamp']), 'journey_dur': int(car['duration']), 'hod': car['hod']})
            #f.write(str(car['timestamp']) + "," + str(car['duration']) + "," + str(car['hod']))
    print("Found {} car journey(s).".format(car_count))
    if save_data_files:
        nf = "{:02d}{:02d}{:02d}{:02d}{:02d}".format(rec_date.month, rec_date.day, rec_date.hour, rec_date.minute, rec_date.second)
        fname = get_traffic(total_car_count) + ".sample" + nf + ".csv"
        if car_count == 0:
            print("NOTE: No cars detected, using default values!")
            final.append({'timestamp': 1000, 'journey_dur': 1000, 'hod': 0} )
        with open(fname, "w", encoding="UTF8", newline="") as csvf:
            writer = csv.DictWriter(csvf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final)
        print("SAVED_DATA_FILE=True; Saved to file: {}".format(fname))

    if inference_on:
        # convert final to new format - temporary?
        journey_sum = 0
        hod = 0
        for item in final:
            journey_sum = journey_sum + int(item['journey_dur'])
            hod = item['hod']  # will only get last value
        final_mod = [car_count, journey_sum/car_count]
        print("Final mod: {}".format(final_mod)) 
        with open("features.txt", "w", encoding="UTF8", newline="") as csvf:
            writer = csv.writer(csvf)
            #writer.writeheader()
            writer.writerow(final_mod)
        print("INFERENCE_ON=True; Saved features.txt")

def EI_inference():
    #
    # Uses local model file to perform inference on collected data
    #

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
        print("classification:")
        print(res["result"])
        print("timing:")
        print(res["timing"])

    finally:
        if (runner):
            runner.stop()

# Start here

while True:
    print("-----------------------------------------------")
    r = requests.get("http://opendatacam:8080/recording/start")
    print("Started recording {} for next {} second(s)...".format(recording_count, sample_interval))
    print("Response from odc: {}".format(r.text))
    started = datetime.datetime.now()
    started_formatted = "{:02d}{:02d}{:02d}{:02d}{:02d}".format(started.month, started.day, started.hour, started.minute, started.second)
    print("Started recording file: {}.".format(started_formatted))
    interval_qtr = sample_interval/4
    time.sleep(interval_qtr)
    print("{} s. remaining...".format(interval_qtr * 3), end = " ")
    time.sleep(interval_qtr)
    print("{} s. remaining...".format(interval_qtr * 2))
    time.sleep(interval_qtr)
    print("{} s. remaining...".format(interval_qtr), end = " ")
    time.sleep(interval_qtr)
    print("Stopping recording...")
    r = requests.get("http://opendatacam:8080/recording/stop")
    rr = get_last_recording()
    save_rec_data(rr)
    
    if inference_on:
        # Call EI inference code here
        EI_inference()
   
    if upload_data_files:
        # Upload files back to EI for training
        pass

    recording_count = recording_count + 1

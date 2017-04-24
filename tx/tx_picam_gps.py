#!/usr/bin/env python
#
#	PiCam Transmitter Script - with GPS Data and Logo Overlay.
#	Capture images from the PiCam, and transmit them.
#
#	Mark Jessop <vk5qi@rfhead.net>
#

import PacketTX
import WenetPiCam
import ublox
import argparse
import time
import os
import subprocess
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("callsign", default="N0CALL", help="Payload Callsign")
parser.add_argument("--gps", default="/dev/ttyACM0", help="uBlox GPS Serial port. Defaults to /dev/ttyACM0")
parser.add_argument("--logo", default="none", help="Optional logo to overlay on image.")
parser.add_argument("--txport", default="/dev/ttyAMA0", type=str, help="Transmitter serial port. Defaults to /dev/ttyAMA0")
parser.add_argument("--baudrate", default=115200, type=int, help="Transmitter baud rate. Defaults to 115200 baud.")
args = parser.parse_args()

callsign = args.callsign
# Truncate callsign if it's too long.
if len(callsign) > 6:
	callsign = callsign[:6]

print("Using Callsign: %s" % callsign)


# Start up Wenet TX.
tx = PacketTX.PacketTX(serial_port=args.txport, serial_baud=args.baudrate, callsign=callsign, log_file="debug.log")
tx.start_tx()

# Sleep for a second to let the transmitter fire up.
time.sleep(1)

# Initialise a couple of global variables.
max_altitude = 0
system_time_set = False

def handle_gps_data(gps_data):
	""" Handle GPS data passed to us from the UBloxGPS instance """
	global max_altitude, tx, system_time_set

	# Immediately generate and transmit a GPS packet.
	tx.transmit_gps_telemetry(gps_data)

	# If we have GPS fix, update the max altitude field.
	if (gps_data['altitude'] > max_altitude) and (gps_data['gpsFix'] == 3):
		max_altitude = gps_data['altitude']

	# If we have GPS lock, set the system clock to it. (Only do this once.)
	if (gps_data['gpsFix'] == 3) and not system_time_set:
		dt = gps_data['datetime']
		try:
			subprocess.call(['date', '-s', '{:}'.format(dt.strftime('%Y/%m/%d %H:%M:%S'))], shell=True)
			tx.transmit_text_message("GPS Debug: System clock set to GPS time %s" % gps_data['timestamp'])
			system_time_set = True
		except:
			tx.transmit_text_message("GPS Debug: Attempt to set system clock failed!")



# Try and start up the GPS rx thread.
try:
	gps = ublox.UBloxGPS(port=args.gps, 
		dynamic_model = ublox.DYNAMIC_MODEL_AIRBORNE1G, 
		update_rate_ms = 1000,
		debug_ptr = tx.transmit_text_message,
		callback = handle_gps_data,
		log_file = 'gps_data.log'
		)
except Exception as e:
	tx.transmit_text_message("ERROR: Could not Open GPS - %s" % str(e), repeats=5)
	gps = None

# Define our post-processing callback function, which gets called by WenetPiCam
# after an image has been captured.
def post_process_image(filename):
	""" Post-process the image, adding on Logo overlay and GPS data if requested. """
	global gps, max_altitude, args, tx

	# Try and grab current GPS data snapshot
	try:
		if gps != None:
			gps_state = gps.read_state()

			# Format time
			short_time = gps_state['datetime'].strftime("%Y-%m-%d %H:%M:%S")

			# Construct string which we will add onto the image.
			if gps_state['numSV'] < 3:
				# If we don't have enough sats for a lock, don't display any data.
				# TODO: Use the GPS fix status values here instead.
				gps_string = "No GPS Lock"
			else:
				gps_string = "%s Lat: %.5f   Lon: %.5f  Alt: %dm (%dm)  Speed: H %03.1f kph  V %02.1f m/s" % (
					short_time,
					gps_state['latitude'],
					gps_state['longitude'],
					int(gps_state['altitude']),
					int(max_altitude),
					gps_state['ground_speed'],
					gps_state['ascent_rate'])
		else:
			gps_string = "No GPS"
	except:
		error_str = traceback.format_exc()
		self.debug_message("GPS Data Access Failed: %s" % error_str)
		gps_string = "GPS Failure"

	# Build up our imagemagick 'convert' command line
	overlay_str = "convert %s -gamma 0.8 -font Helvetica -pointsize 30 -gravity North " % filename 
	overlay_str += "-strokewidth 2 -stroke '#000C' -annotate +0+5 \"%s\" " % gps_string
	overlay_str += "-stroke none -fill white -annotate +0+5 \"%s\" " % gps_string
	# Add on logo overlay argument if we have been given one.
	if args.logo != "none":
		overlay_str += "%s -gravity SouthEast -composite " % args.logo

	overlay_str += filename

	tx.transmit_text_message("Adding overlays to image.")
	os.system(overlay_str)

	return


# Finally, initialise the PiCam capture object.
picam = WenetPiCam.WenetPiCam(src_resolution=(1920,1088), 
		tx_resolution=(1920,1088), 
		callsign=callsign, 
		num_images=5, 
		debug_ptr=tx.transmit_text_message, 
		vertical_flip=False, 
		horizontal_flip=False)
# .. and start it capturing continuously.
picam.run(destination_directory="./tx_images/", 
	tx = tx,
	post_process_ptr = post_process_image
	)


# Main 'loop'.
try:
	while True:
		# Do nothing!
		# Sleep to avoid chewing up CPU cycles in this loop.
		time.sleep(1)
# Catch CTRL-C, and exit cleanly.
# Only really used during debugging.
except KeyboardInterrupt:
	print("Closing")
	picam.stop()
	tx.close()
	gps.close()

















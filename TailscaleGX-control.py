#!/usr/bin/env python
#
#	TailscaleGX-control.py
#	Kevin Windrem
#
# This program controls remote access to a Victron Energy
# It is based on tailscale which is based on WireGauard.
#
# This runs as a daemon tools service at /service/TailscaleGx-control
#
# ssh and html (others TBD) connections can be made via
#	the IP address(s) supplied by the tailscale broker.
#
# Persistent storage for TailscaleGX is stored in dbus Settings:
#
#	com.victronenergy.Settings parameters:
#		/Settings/TailscaleGX/Enabled
#			controls wheter remote access is enabled or disabled
#
# Operational parameters are provided by:
#	com.victronenergy.tailscaleGX
#		/State
#		/IPv4		IP v4 remote access IP address
#		/IPv6		as above for IP v6
#		/HostName	as above but as a host name
#		/LoginLink	temorary URL for connecting to tailscale
#						for initiating a connection
#		/GuiCommand	GUI writes string here to request an action:
#			logout
#
# together, the above settings and dbus service provide the condiut to the GUI
#
# On startup the dbus settings and service are created
#	control then passes to mainLoop which gets scheduled once per second:
#		starts / stops the TailscaleGX-backend based on /Enabled
#		scans status from tailscale link
#		TBD
#		TBD
#		TBD
#		provides status and prompting to the GUI during this process
#			in the end providing the user the IP address they must use
#			to connect to the GX device.
#

import platform
import argparse
import logging
import sys
import subprocess
import threading
import os
import shutil
import dbus
import time
import re

PythonVersion = sys.version_info
# accommodate both Python 2 (prior to v2.80) and 3
if PythonVersion >= (3, 0):
	import queue
	from gi.repository import GLib
else:
	import Queue as queue
	import gobject as GLib

# convert a version string to an integer to make comparisions easier
# refer to PackageManager.py for full description

def VersionToNumber (version):
	version = version.replace ("large","L")
	numberParts = re.split ('\D+', version)
	otherParts = re.split ('\d+', version)
	# discard blank elements
	#	this can happen if the version string starts with alpha characters (like "v")
	# 	of if there are no numeric digits in the version string
	try:
		while numberParts [0] == "":
			numberParts.pop(0)
	except:
		pass

	numberPartsLength = len (numberParts)

	if numberPartsLength == 0:
		return 0
	versionNumber = 0
	releaseType='release'
	if numberPartsLength >= 2:
		if 'b' in otherParts or '~' in otherParts:
			releaseType = 'beta'
			versionNumber += 60000
		elif 'a' in otherParts:
			releaseType = 'alpha'
			versionNumber += 30000
		elif 'd' in otherParts:
			releaseType = 'develop'

	# if release all parts contribute to the main version number
	#	and offset is greater than all prerelease versions
	if releaseType == 'release':
		versionNumber += 90000
	# if pre-release, last part will be the pre release part
	#	and others part will be part the main version number
	else:
		numberPartsLength -= 1
		versionNumber += int (numberParts [numberPartsLength])

	# include core version number
	versionNumber += int (numberParts [0]) * 10000000000000
	if numberPartsLength >= 2:
		versionNumber += int (numberParts [1]) * 1000000000
	if numberPartsLength >= 3:
		versionNumber += int (numberParts [2]) * 100000

	return versionNumber


# get venus version
versionFile = "/opt/victronenergy/version"
try:
	file = open (versionFile, 'r')
except:
	VenusVersion = ""
	VenusVersionNumber = 0
else:
	VenusVersion = file.readline().strip()
	VenusVersionNumber = VersionToNumber (VenusVersion)
	file.close()

# add the path to our own packages for import
# use an established Victron service to maintain compatiblity
setupHelperVeLibPath = "/data/SetupHelper/velib_python"
veLibPath = ""
if os.path.exists ( setupHelperVeLibPath ):
	for libVersion in os.listdir ( setupHelperVeLibPath ):
		# use 'latest' for newest versions even if not specifically checked against this verison when created
		if libVersion == "latest":
			newestVersionNumber = VersionToNumber ( "v9999.9999.9999" )
		else:
			newestVersionNumber = VersionToNumber ( libVersion )
		oldestVersionPath = os.path.join (setupHelperVeLibPath, libVersion, "oldestVersion" )
		if os.path.exists ( oldestVersionPath ):
			try:
				fd = open (oldestVersionPath, 'r')
				oldestVersionNumber = VersionToNumber ( fd.readline().strip () )
				fd.close()
			except:
				oldestVersionNumber = 0
		else:
			oldestVersionNumber = 0
		if VenusVersionNumber >= oldestVersionNumber and VenusVersionNumber <= newestVersionNumber:
			veLibPath = os.path.join (setupHelperVeLibPath, libVersion)
			break

# no SetupHelper velib - use one in systemcalc
if veLibPath == "":
	veLibPath = os.path.join('/opt/victronenergy/dbus-systemcalc-py', 'ext', 'velib_python')

logging.warning ("using " + veLibPath + " for velib_python")
sys.path.insert(1, veLibPath)

from vedbus import VeDbusService
from settingsdevice import SettingsDevice




# sends a unix command
#	eg sendCommand ( [ 'svc', '-u' , serviceName ] )
#
# stdout, stderr and the exit code are returned as a list to the caller

def sendCommand ( command=None ):
	if command == None:
		logging.error ( "sendCommand: no command specified" )
		return None, None, None
	try:
		proc = subprocess.Popen ( command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	except:
		logging.error ("sendCommand: " + command + " failed")
		return None, None, None
	else:
		out, err = proc.communicate ()
		stdout = out.decode ().strip ()
		stderr = err.decode ().strip ()
		return stdout, stderr, proc.returncode


tsControlCmd = '/data/TailscaleGX/tailscale'


# static variables for main and mainLoop
DbusSettings = None
DbusService = None


UNKNOWN_STATE = 0
BACKEND_STARTING = 1
NOT_RUNNING = 2
STOPPED = 3
LOGGED_OUT = 4
WAIT_FOR_RESPONSE = 5
CONNECT_WAIT = 6
CONNECTED = 100

global previousState
global state
global systemNameObj
global systemName
global hostName
global ipV4

previousState = UNKNOWN_STATE
state = UNKNOWN_STATE
systemNameObj = None
systemName = None
hostName = None
ipV4 = ""

def mainLoop ():
	global DbusSettings
	global DbusService
	global previousState
	global state
	global systemName
	global hostName
	global ipV4

	startTime = time.time ()

	backendRunning = None
	tailscaleEnabled = False
	thisHostName = None

	loginInfo = ""

	if systemNameObj == None:
		systemName = None
		hostName = None
	else:
		name = systemNameObj.GetValue ()
		if name != systemName:
			systemName = name
			if name == None or name == "":
				hostName = None
				logging.warning ("no system name so no host name" )
			else:
				# some characters permitted for the GX system name aren't valid as a URL name
				# so replace them with '-'
				name = re.sub("[!@#$%^&*()\[\]{};:,./<>?\|`'~=_+ ]", "-", name)
				name = name.replace ('\\', '-')
				# host name must start with a letter or number
				name = name.strip(' -').lower ()
				hostName = name
				logging.info ("system name changed to " + systemName)
				logging.info ("new host name " + hostName + " will be used on NEXT login" )

	# see if backend is running
	stdout, stderr, exitCode = sendCommand ( [ 'svstat', "/service/TailscaleGX-backend" ] )
	if stdout == None:
		logging.warning ("TailscaleGX-backend not in services")
		backendRunning = None
	elif stderr == None or "does not exist" in stderr:
		logging.warning ("TailscaleGX-backend not in services")
		backendRunning = None
	elif stdout != None and ": up" in stdout:
		backendRunning = True
	else:
		backendRunning = False

	tailscaleEnabled = DbusSettings ['enabled'] == 1

	# start backend
	if tailscaleEnabled and backendRunning == False:
		logging.info ("starting TailscaleGX-backend")
		_, _, exitCode = sendCommand ( [ 'svc', '-u', "/service/TailscaleGX-backend"] )
		if exitCode != 0:
			logging.error ( "start TailscaleGX failed " + str (exitCode) )
		state = BACKEND_STARTING
	# stop backend
	elif not tailscaleEnabled and backendRunning == True:
		logging.info ("stopping TailscaleGX-backend")
		_, _, exitCode = sendCommand ( [ 'svc', '-d', "/service/TailscaleGX-backend"] )
		if exitCode != 0:
			logging.error ( "stop TailscaleGX failed " + str (exitCode) )
		backendRunning = False

	if backendRunning:

		# check for GUI commands and act on them
		guiCommand = DbusService['/GuiCommand']
		if guiCommand != "":
			# acknowledge receipt of command so another can be sent
			DbusService['/GuiCommand'] = ""
			if guiCommand == 'logout':
				logging.info ("logout command received")
				# logout takes time and can't specify a timeout so provide feedback first
				DbusService['/State'] = WAIT_FOR_RESPONSE
				_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'logout' ] )
				if exitCode != 0:
					logging.error ( "tailscale logout failed " + str (exitCode) )
					logging.error (stderr)
				else:
					state = WAIT_FOR_RESPONSE
			else:
				logging.warning ("invalid command received " + guiCommand)

		# get current status from tailscale and update state
		stdout, stderr, exitCode = sendCommand ( [ tsControlCmd, 'status' ] )
		# don't update state if we don't get a response
		if stdout == None or stderr == None:
			pass
		elif "failed to connect" in stderr:
			state = NOT_RUNNING
		elif "Tailscale is stopped" in stdout:
			state = STOPPED
		elif "Log in at" in stdout:
			state = CONNECT_WAIT
			lines = stdout.splitlines ()
			loginInfo = lines[1].replace ("Log in at: ", "")
		elif "Logged out" in stdout:
			# can get back to this condition while loggin in
			# so wait for another condition to update state
			if previousState != WAIT_FOR_RESPONSE:
				state = LOGGED_OUT
		elif exitCode == 0:
			state = CONNECTED
			# extract this host's name from status message
			if ipV4 != "":
				for line in stdout.splitlines ():
					if ipV4 in line:
							thisHostName = line.split()[1]

		# don't update state if we don't recognize the response
		else:
			pass

		# make changes necessary to bring connection up
		#	up will fully connect if login had succeeded
		#	or ask for login if not
		#	next get syatus pass will indicate that
		# call is made with a short timeout so we can monitor status
		#	but need to defer future tailscale commands until
		#	tailscale has processed the first one
		#	ALMOST any state change will signal the wait is over
		#	(status not included)
		if state != previousState:
			if state == STOPPED and previousState != WAIT_FOR_RESPONSE:
				if systemName == None or systemName == "":
					logging.info ("starting tailscale without host name")
					_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'up',
								'--timeout=0.1s' ] )
				else:
					logging.info ("starting tailscale with host name:" + hostName)
					_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'up',
								'--timeout=0.1s', '--hostname=' + hostName ] )
				if exitCode != 0:
					logging.error ( "tailscale up failed " + str (exitCode) )
					logging.error (stderr)
				else:
					state = WAIT_FOR_RESPONSE
			elif state == LOGGED_OUT and previousState != WAIT_FOR_RESPONSE:
				if systemName == None or systemName == "":
					logging.info ("logging in to tailscale without host name")
					_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'login',
								'--timeout=0.1s' ], )
				else:
					logging.info ("logging in to tailscale with host name:" + hostName)
					_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'login', 
								'--timeout=0.1s', '--hostname=' + hostName ] )
				if exitCode != 0:
					logging.error ( "tailscale login failed " + str (exitCode) )
					logging.error (stderr)
				else:
					state = WAIT_FOR_RESPONSE

		# show IP addresses only if connected
		if state == CONNECTED:
			if previousState != CONNECTED:
				logging.info ("connection successful")
			stdout, stderr, exitCode = sendCommand ( [ tsControlCmd, 'ip' ] )
			if exitCode != 0:
				logging.error ( "tailscale ip failed " + str (exitCode) )
				logging.error (stderr)
			if stdout != None and stdout != "":
				ipV4, ipV6 = stdout.splitlines ()
				DbusService['/IPv4'] = ipV4
				DbusService['/IPv6'] = ipV6
			else:
				DbusService['/IPv4'] = "?"
				DbusService['/IPv6'] = "?"
			DbusService['/HostName'] = thisHostName
		else:
			DbusService['/IPv4'] = ""
			DbusService['/IPv6'] = ""
			DbusService['/HostName'] = ""

	else:
		state = NOT_RUNNING

	# update dbus values regardless of state of the link
	DbusService['/State'] = state
	DbusService['/LoginLink'] = loginInfo

	previousState = state
	#### TODO: enable for testing
	endTime = time.time ()
	####print ("main loop time %3.1f mS" % ( (endTime - startTime) * 1000 ))
	return True

def main():
	global DbusSettings
	global DbusService
	global systemNameObj

	# fetch installed version
	installedVersionFile = "/etc/venus/installedVersion-TailscaleGX-control"
	try:
		versionFile = open (installedVersionFile, 'r')
	except:
		installedVersion = ""
	else:
		installedVersion = versionFile.readline().strip()
		versionFile.close()
		# if file is empty, an unknown version is installed
		if installedVersion ==  "":
			installedVersion = "unknown"

	# set logging level to include info level entries
	logging.basicConfig( format='%(levelname)s:%(message)s', level=logging.INFO )

	logging.info (">>>> TailscaleGX-control" + installedVersion + " starting")

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	from dbus.mainloop.glib import DBusGMainLoop
	DBusGMainLoop(set_as_default=True)
	global PythonVersion
	if PythonVersion < (3, 0):
		GLib.threads_init()

	theBus = dbus.SystemBus()
	dbusSettingsPath = "com.victronenergy.settings"

	settingsList = {'enabled': [ '/Settings/TailscaleGX/Enabled', 0, 0, 1 ] }
	DbusSettings = SettingsDevice(bus=theBus, supportedSettings=settingsList,
					timeout = 30, eventCallback=None )

	DbusService = VeDbusService ('com.victronenergy.tailscaleGX', bus = dbus.SystemBus())
	DbusService.add_mandatory_paths (
						processname = 'TailscaleGX-control', processversion = 1.0, connection = 'none',
						deviceinstance = 0, productid = 1,
						productname = 'TailscaleGX-control',
						firmwareversion = 1, hardwareversion = 0, connected = 1)

	DbusService.add_path ( '/State', "" )
	DbusService.add_path ( '/IPv4', "" )
	DbusService.add_path ( '/IPv6', "" )
	DbusService.add_path ( '/HostName', "" )
	DbusService.add_path ( '/LoginLink', "" )

	DbusService.add_path ( '/GuiCommand', "", writeable = True )

	systemNameObj = theBus.get_object (dbusSettingsPath, "/Settings/SystemSetup/SystemName")


	# call the main loop - every 1 second
	# this section of code loops until mainloop quits
	GLib.timeout_add(1000, mainLoop)
	mainloop = GLib.MainLoop()
	mainloop.run()

	logging.critical ("TailscaleGX-control exiting")

main()

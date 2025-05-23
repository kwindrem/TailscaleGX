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
#		/Settings/TailscaleGX/IpForwarding
#			controls whether the GX device is set to forward IP traffic to other nodes
#
# Operational parameters are provided by:
#	com.victronenergy.tailscaleGX
#		/State
#		/IPv4		IP v4 remote access IP address
#		/IPv6		as above for IP v6
#		/HostName	as above but as a host name
#		/LoginLink	temorary URL for connecting to tailscale
#						for initiating a connection
#		/AuthKey	tailscale authorization key (optional connection mechanism)
#		/GuiCommand	GUI writes string here to request an action:
#			logout
#
# together, the above settings and dbus service provide the condiut to the GUI
#
# On startup the dbus settings and service are created
#	control then passes to mainLoop which gets scheduled once per second:
#		starts / stops the TailscaleGX-backend based on /Enabled
#			IP forwarding is also set during starting and stopping
#		scans status from tailscale link
#		scans status from tailscale lin
#		provides status and prompting to the GUI during this process
#			in the end providing the user the IP address they must use
#			to connect to the GX device.
#
# Note: tailscale will be integrated into stock firmware
#	when this happens, TailscaleGX will not run

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
from gi.repository import GLib
# add the path to our own packages for import
sys.path.insert(1, "/data/SetupHelper/velib_python")
from vedbus import VeDbusService
from settingsdevice import SettingsDevice


# sends a unix command
#	eg sendCommand ( [ 'svc', '-u' , serviceName ] )
#
# stdout, stderr and the exit code are returned as a list to the caller

def sendCommand ( command=None, hostName=None, authKey=None ):
	if command == None:
		logging.error ( "sendCommand: no command specified" )
		return None, None, None

	if hostName != None and hostName != "":
		command += [ "--hostname=" + hostName ]
	if authKey != None and authKey != "":
		command += [ "--auth-key=" + authKey ]

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

# state values
UNKNOWN_STATE = 0
BACKEND_STARTING = 1
NOT_RUNNING = 2
STOPPED = 3
LOGGED_OUT = 4
WAIT_FOR_RESPONSE = 5
CONNECT_WAIT = 6
CONNECTED = 100
CHECK_AUTH_KEY = 200

global previousState
global state
global systemNameObj
global systemName
global hostName
global ipV4
global lastIpForwardingEnabled

previousState = UNKNOWN_STATE
state = UNKNOWN_STATE
systemNameObj = None
systemName = None
hostName = None
ipV4 = ""
lastIpForwardingEnabled = False
authKey = ""
lastResponseTime = 0
checkAuthKey = False

def mainLoop ():
	global DbusSettings
	global DbusService
	global previousState
	global state
	global systemName
	global hostName
	global ipV4
	global lastIpForwardingEnabled
	global authKey
	global lastResponseTime
	global checkAuthKey

	startTime = time.time ()

	backendRunning = None
	tailscaleEnabled = False
	ipForwardingEnabled = False
	thisHostName = None

	loginInfo = ""

	if systemNameObj == None:
		systemName = None
		hostName = ""
	else:
		name = systemNameObj.GetValue ()
		if name != systemName:
			systemName = name
			if name == None or name == "":
				hostName = ""
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
	if tailscaleEnabled and state == CONNECTED:
		ipForwardingEnabled = DbusSettings ['customArguements'] == "--advertise-exit-node=true"
	else:
		ipForwardingEnabled = ""

	# update IP forwarding and exit-node enable
	if ipForwardingEnabled != lastIpForwardingEnabled:
		lastIpForwardingEnabled = ipForwardingEnabled
		if ipForwardingEnabled:
			logging.info ("IP forwarding enabled")
			enabled = '1'
			enabled2 = "true"
		else:
			logging.info ("IP forwarding disabled")
			enabled = '0'
			enabled2 = "false"
		_, _, exitCode = sendCommand ( [ 'sysctl', '-w', "net.ipv4.ip_forward=" + enabled ] )
		if exitCode != 0:
			logging.error ( "could not change IP v4 forwarding state to " + enabled + " " + str (exitCode) )
		_, _, exitCode = sendCommand ( [ 'sysctl', '-w', "net.ipv6.conf.all.forwarding=" + enabled ] )
		if exitCode != 0:
			logging.error ( "could not change IP v6 forwarding state to " + enabled + " " + str (exitCode) )
		_, _, exitCode = sendCommand ( [ tsControlCmd, 'set', "--advertise-exit-node=" + enabled2 ] )
		if exitCode != 0:
			logging.error ( "could not change tailscale exit-node setting to " + enabled2 + " " + str (exitCode) )

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
		resetConnection = False

		# check for GUI commands and act on them
		guiCommand = DbusService['/GuiCommand']
		if guiCommand != "":
			# acknowledge receipt of command so another can be sent
			DbusService['/GuiCommand'] = ""
			if guiCommand == 'logout':
				logging.info ("logout command received")
				resetConnection = True
				lastResponseTime = startTime

		newAuthKey = DbusSettings ['authKey']
		if newAuthKey == None:
			newAuthKey = ""
		if newAuthKey != authKey and newAuthKey != None and newAuthKey != "":
			logging.info ("new auth key detected")
			resetConnection = True
			checkAuthKey = False
		authKey = newAuthKey

		# get current status from tailscale and update state
		stdout, stderr, exitCode = sendCommand ( [ tsControlCmd, 'status' ] )
		# don't update state if we don't get a response
		if stdout == None or stderr == None:
			logging.error ("no response to status command")
			checkAuthKey = False
			pass
		elif "failed to connect" in stderr:
			state = NOT_RUNNING
			checkAuthKey = False
		elif "Tailscale is stopped" in stdout:
			state = STOPPED
		elif "Log in at" in stdout and authKey == "":
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
			checkAuthKey = False
			# extract this host's name from status message
			if ipV4 != "":
				for line in stdout.splitlines ():
					if ipV4 in line:
						thisHostName = line.split()[1]

		# don't update state if we don't recognize the response
		else:
			pass

		# response timeout indicates no internet connection to tailscale server
		#  or possibly bad auth key
		if state == WAIT_FOR_RESPONSE and authKey != "":
			if lastResponseTime != 0 and startTime - lastResponseTime > 30:
				logging.error ("timeout waiting for response from tailscale - check auth key")
				resetConnection = True
				checkAuthKey = True
		else:
			lastResponseTime = startTime


		# make changes necessary to bring connection up
		#	up will fully connect if login had succeeded
		#	or ask for login if not
		#	next get syatus pass will indicate that
		# call is made with a short timeout so we can monitor status
		#	but need to defer future tailscale commands until
		#	tailscale has processed the first one
		#	ALMOST any state change will signal the wait is over
		#	(status not included)

		# resetConnection logs out of tailscale
		# so that a new connection can be made
		# this will occur automatically if an auth key is set
		# otherwise, a message to manually connect via tailscale admin console is displayed
		if resetConnection:
			if authKey == "":
				logging.info ( "resetting connetion for manual connection" )
			else:
				logging.info ( "resetting connetion for new auth key: " + authKey)
			# logout takes time and can't specify a timeout so provide feedback first
			DbusService['/State'] = WAIT_FOR_RESPONSE
			state = WAIT_FOR_RESPONSE
			_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'logout' ] )
			if exitCode != 0:
				logging.error ( "tailscale logout failed " + str (exitCode) )
				logging.error (stderr)
			else:
				state = LOGGED_OUT
		elif state == STOPPED:
			logging.info ("starting tailscale " + hostName + " " + authKey)
			_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'up',
						'--timeout=0.1s' ], hostName=hostName, authKey=authKey )
			if exitCode != 0 and not "timeout" in stderr:
				logging.error ( "tailscale up failed " + str (exitCode) )
				logging.error (stderr)
			else:
				state = WAIT_FOR_RESPONSE
		elif state == LOGGED_OUT:
			logging.info ("logging in to tailscale " + hostName + " " + authKey)
			_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'login',
						'--timeout=0.1s' ], hostName=hostName, authKey=authKey )
			if exitCode != 0 and not "timeout" in stderr:
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
		checkAuthKey = False

	# update dbus values regardless of state of the link
	if checkAuthKey:
		DbusService['/State'] = CHECK_AUTH_KEY
	else:
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
	installedVersionFile = "/etc/venus/installedVersion-TailscaleGX"
	try:
		versionFile = open (installedVersionFile, 'r')
	except:
		installedVersion = "(version unknown)"
	else:
		installedVersion = versionFile.readline().strip()
		versionFile.close()
		# if file is empty, an unknown version is installed
		if installedVersion ==  "":
			installedVersion = "(version unknown)"

	# set logging level to include info level entries
	logging.basicConfig( format='%(levelname)s:%(message)s', level=logging.INFO )

	logging.info (">>>> TailscaleGX-control" + installedVersion + " starting")

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	from dbus.mainloop.glib import DBusGMainLoop
	DBusGMainLoop(set_as_default=True)

	theBus = dbus.SystemBus()
	dbusSettingsPath = "com.victronenergy.settings"

	settingsList =	{ 'enabled': [ '/Settings/Services/Tailscale/Enabled', 0, 0, 1 ],
					  'customArguements': [ '/Settings/Services/Tailscale/CustomArguments', "", 0, 0 ],
					  'authKey' :  [ '/Settings/Services/Tailscale/AuthKey', "", 0, 0 ]
					}
	DbusSettings = SettingsDevice(bus=theBus, supportedSettings=settingsList,
					timeout = 30, eventCallback=None )

	# migrate settings and tailscale state directory
	removeSettings = False
	try:
		oldSettingObj = theBus.get_object (dbusSettingsPath, "/Settings/TailscaleGX/Enabled")
		oldSetting=oldSettingObj.GetValue()
		logging.warning ( "moving enabled setting to new location and removing old loction" )
		DbusSettings['enabled'] = oldSetting
		removeSettings = True
	except:
		pass
	try:
		oldSettingObj = theBus.get_object (dbusSettingsPath, "/Settings/TailscaleGX/IpForwarding")
		oldSetting=oldSettingObj.GetValue()
		logging.warning ( "moving IP forwarding setting to new location and removing old loction" )
		if oldSetting:
			DbusSettings['customArguements'] = "--advertise-exit-node=true"
		else:
			DbusSettings['customArguements'] = ""
		removeSettings = True
	except:
		pass

	# remove old settings
	if removeSettings:
		settingsToRemove = '%[ "' + "/Settings/TailscaleGX/Enabled" + '" , "' + "/Settings/TailscaleGX/IpForwarding" + '" ]'
		sendCommand ( ['dbus', '-y', 'com.victronenergy.settings', '/', 'RemoveSettings', settingsToRemove  ] )

	stockTailscaleStateDir = "/data/conf/tailscale"
	oldStateDir = "/data/setupOptions/TailscaleGX/state"
	if os.path.exists ( oldStateDir ) and not os.path.exists ( stockTailscaleStateDir ):
		logging.warning ( "moving tailscale state to new location" )
		shutil.move ( oldStateDir, stockTailscaleStateDir )

	if os.path.exists ("/opt/victronenergy/tailscale"):
		logging.warning ("tailscale is now part of stock firmware - TailscaleGX-control no longer used - exiting")
		sendCommand ( [ 'svc', '-d' , "/service/TailscaleGX-control" ] )
		exit ()

	DbusService = VeDbusService ('com.victronenergy.tailscaleGX', bus = dbus.SystemBus(), register=False)
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

	DbusService.register ()


	systemNameObj = theBus.get_object (dbusSettingsPath, "/Settings/SystemSetup/SystemName")

	# call the main loop - every 1 second
	# this section of code loops until mainloop quits
	GLib.timeout_add(1000, mainLoop)
	mainloop = GLib.MainLoop()
	mainloop.run()

	logging.critical ("TailscaleGX-control exiting")

main()

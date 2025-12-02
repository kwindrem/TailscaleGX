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
#		/LoginServerUrl	an alternate login server (eg Headscale) ("" if using tailscale's server)
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
from urllib.parse import urlparse
from gi.repository import GLib
# add the path to our own packages for import
sys.path.insert(1, "/data/SetupHelper/velib_python")
from vedbus import VeDbusService
from settingsdevice import SettingsDevice
import json


# sends a unix command
#	eg sendCommand ( [ 'svc', '-u' , serviceName ] )
#
# stdout, stderr and the exit code are returned as a list to the caller
#
# use the following return codes
#	124: timeout: command aborted (timeout must be set or sendCommand never returns)
#	126: command not executable (e.g., due to incorrect permissions).
#	127: command not found
#	otherwise the process exit code is returned to caller of sendCommand
#		this will typically be 0 on success and any other value on failure

global lastSendCommandException
lastSendCommandException = None

def sendCommand ( command=None, loginServer=None, hostName=None, authKey=None, timeout=None ):
	global lastSendCommandException

	if command == None:
		logging.error ( "sendCommand: no command specified" )
		return "", "", 127

	if loginServer != None and loginServer != "":
		command += [ "--login-server=" + loginServer ]
	if hostName != None and hostName != "":
		command += [ "--hostname=" + hostName ]
	if authKey != None and authKey != "":
		command += [ "--auth-key=" + authKey ]

	try:
		proc = subprocess.Popen ( command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		stdout, stderr = proc.communicate (timeout=timeout)
	except subprocess.TimeoutExpired:
			return "", "", 124
	except Exception as ex:
		newType = type (ex)
		newArgs = ex.args
		if lastSendCommandException == None:
			lastType = None
			lastArgs = None
		else:
			lastType = type (lastSendCommandException)
			lastArgs = ex.args
		if lastSendCommandException == None or newType != lastType or newArgs != lastArgs:
			logging.error ("sendCommand: " + str (command) + " failed: " + str (ex) )
		lastSendCommandException = ex
		return "", "", 126
	else:
		stdout = stdout.strip ()
		stderr = stderr.strip ()
		return stdout, stderr, proc.returncode


tsControlCmd = '/data/TailscaleGX/tailscale'


# static variables for main and mainLoop
DbusSettings = None
DbusService = None

# state values
UNKNOWN_STATE = 0
BACKEND_STARTING = 1
BACKEND_NOT_RUNNING = 2
CLIENT_STOPPED = 3
LOGGED_OUT = 4
WAIT_FOR_RESPONSE = 5
CONNECT_WAIT = 6
STATUS_TIMEOUT = 7
CLIENT_STARTING = 8
LOGIN_WAIT = 9
IN_USE = 10
MACH_AUTH = 11
NETWORK_DOWN = 12
CONNECTED = 100

INIT = 99
# state value for UI only
SERVER_ERROR = 201
CLIENT_ERROR = 202

global previousState
global state
global systemNameObj
global systemName
global hostName
global loginServer
global loginServerUrl
global resetConnection
global restartBackend
global serverReached
global lastPingTime

previousState = INIT
state = INIT
systemNameObj = None
systemName = None
hostName = None
authKey = None
lastResponseTime = 0
uiStateOveride = UNKNOWN_STATE
reportClientError = False
loginServer = None
loginServerUrl = None
resetConnection = False
restartBackend = False
serverReached = False
doLogout = False
lastPingTime = 0

def mainLoop ():
	global DbusSettings
	global DbusService
	global previousState
	global state
	global systemName
	global hostName
	global authKey
	global lastResponseTime
	global uiStateOveride
	global reportClientError
	global loginServer
	global loginServerUrl
	global resetConnection
	global restartBackend
	global doLogout
	global serverReached
	global lastPingTime

	startTime = time.time ()
	if state == INIT:
		lastResponseTime = startTime
		lastPingTime = startTime
		restartBackend = False
		uiStateOveride = UNKNOWN_STATE

	tailscaleEnabled = False
	ipForwardingEnabled = False
	thisHostName = ""
	loginInfo = ""
	backendState = ""
	authUrl = ""
	ip1 = ""
	ip2 = ""
	keyExpiry = ""
	tailnetName = ""

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
			logging.info ("new system name: " + systemName + "  new host name: " + hostName)
			if state != INIT:
				resetConnection = True

	# check for GUI commands and act on them
	guiCommand = DbusService['/GuiCommand']
	if guiCommand != "":
		# acknowledge receipt of command so another can be sent
		DbusService['/GuiCommand'] = ""
		if guiCommand == 'logout':
			logging.info ("logout command received from UI")
			doLogout = True	

	# check if loginServer has changed and is a valiid URL
	newServer = DbusSettings ['loginServer'].strip() # remove accidental spaces
	if newServer == None:
		newServer = ""
	if loginServer == None or newServer != loginServer:
		
		loginServer = newServer
		loginServerUrl = newServer
		if loginServer != "":
			if not (loginServerUrl.startswith("https://") or loginServerUrl.startswith("http://")):
				loginServerUrl = f"https://{loginServer}"
			parsed = urlparse(loginServerUrl)
			if not (parsed.scheme in ['http', 'https'] and parsed.netloc != ""):
				logging.error ("invalid login server: " + loginServerUrl)
				loginServerUrl = ""
		if loginServerUrl != "":
			logging.info ("using login server: " + loginServerUrl)
		else:
			logging.info ("using tailscale's login server")
		if state != INIT:
			resetConnection = True

	newAuthKey = DbusSettings ['authKey']
	if newAuthKey == None:
		newAuthKey = ""
	if authKey == None or newAuthKey != authKey:
		authKey = newAuthKey
		if authKey != "":
			logging.info ("using auth key: " + authKey)
		else:
			logging.info ("auth key disabled - must login at login server")
		if state != INIT:
			resetConnection = True

	# see if backend is running
	stdout, _, _ = sendCommand ( [ 'svstat', "/service/TailscaleGX-backend" ] )
	if ": up" in stdout:
		backendRunning = True
	else:
		backendRunning = False

	tailscaleEnabled = DbusSettings ['enabled'] == 1
	if tailscaleEnabled and state == CONNECTED:
		ipForwardingEnabled = DbusSettings ['customArguements'] == "--advertise-exit-node=true"
	else:
		ipForwardingEnabled = False

	# check to see if network is up before enabling tailscale
	if tailscaleEnabled:
		if loginServer == "":
			pingAddress = "tailscale.com"
		else:
			pingAddress = loginServer
		_, stderr, errorCode = sendCommand ( [ 'ping', '-c1', pingAddress ], timeout = 1.0 )
		if errorCode == 0:
			lastPingTime = startTime
			if not serverReached:
				logging.info ("login server is responding")
				serverReached = True
		# wait a while before a missed ping triggers actions
		elif startTime > lastPingTime + 5:
			if serverReached:
				logging.info ("login server is NOT responding")
			serverReached = False
			state = NETWORK_DOWN
	else:
		serverReached = False

	# stop backend
	if restartBackend or ( not serverReached and backendRunning ) :
		logging.info ("stopping TailscaleGX-backend")
		_, _, exitCode = sendCommand ( [ 'svc', '-d', "/service/TailscaleGX-backend"] )
		if exitCode != 0:
			logging.error ( "stop TailscaleGX failed " + str (exitCode) )
		if state != NETWORK_DOWN:
			state = BACKEND_NOT_RUNNING
		backendRunning = False
		restartBackend = False

	# start backend
	if serverReached and not backendRunning and state != BACKEND_STARTING:
		logging.info ("starting TailscaleGX-backend")
		_, _, exitCode = sendCommand ( [ 'svc', '-u', "/service/TailscaleGX-backend"] )
		if exitCode != 0:
			logging.error ( "start TailscaleGX failed " + str (exitCode) )
		else:
			state = BACKEND_STARTING

	if not backendRunning:
		if state != BACKEND_STARTING and state != NETWORK_DOWN:
			state = BACKEND_NOT_RUNNING
		# update delay to prevent reporting an immediate no response when backend begins
		lastResponseTime = startTime
	else:
		stdout, stderr, exitCode = sendCommand ( [ tsControlCmd, 'status', '--peers=false', '--json=true' ],
					timeout=1.0 )
		if exitCode == 124:
			state = STATUS_TIMEOUT
		elif exitCode > 125:
			state = WAIT_FOR_RESPONSE
		elif exitCode == 0:
			try:
				status = json.loads (stdout)
				backendState = status["BackendState"]
			except Exception as ex:
				logging.error ("Status message json parsing error: ", str (ex.args) )
				backendState = ""
				state = WAIT_FOR_RESPONSE
			if backendState == "NeedsLogin":
				try:
					authUrl = status["AuthURL"]
				except: pass
				if state != CONNECT_WAIT and state != LOGIN_WAIT:
					state = LOGGED_OUT
			elif backendState == "Running":
				state = CONNECTED
				try:
					selfBlock = status["Self"]
					try:
						thisHostName = selfBlock["HostName"]
					except: pass
					try:
						ips = selfBlock["TailscaleIPs"]
						ip1 = ips[0]
						ip2 = ips[1]
					except: pass
					try:
						tailnetName = selfBlock["CapMap"]["tailnet-display-name"][0]
					except: pass
					try:
						keyExpiry = selfBlock["KeyExpiry"]
					except: pass
				except: pass
			elif backendState == "Stopped":
				state = CLIENT_STOPPED
			elif backendState == "Starting":
				state = CLIENT_STARTING
			elif backendState == "NoState":
				state = STATUS_TIMEOUT
			elif backendState == "InUseOtherUser":
				state = IN_USE
			elif backendState == "NeedsMachineAuth":
				state = MACH_AUTH
			else:
				logging.warning ("Unprocessed backendState " + backendState)
		else:
			logging.error ("Error reading status", exitCode)
			state = WAIT_FOR_RESPONSE

		# no timeout currently occurring - update delay
		if state != WAIT_FOR_RESPONSE and state != STATUS_TIMEOUT and state != CONNECT_WAIT:
			lastResponseTime = startTime
			uiStateOveride = UNKNOWN_STATE
		# delay expired - log results and trigger connection reset
		elif lastResponseTime != 0 and startTime - lastResponseTime > 30:
			lastResponseTime = startTime	# reset timer so next error report is spaced by the timer
			if state == STATUS_TIMEOUT:
				uiStateOveride = CLIENT_ERROR
				restartBackend = True
				logging.error ("timeout waiting for response from tailscale client")
			elif state == WAIT_FOR_RESPONSE:
				resetConnection = True
				uiStateOveride = SERVER_ERROR
				if loginServerUrl != "" and authKey != "":
					logging.error ("timeout waiting for response from " + loginServerUrl + " - check URL and auth key")
				elif loginServerUrl != "":
					logging.error ("timeout waiting for response from " + loginServerUrl + " - check URL")
				elif authKey != "":
					logging.error ("timeout waiting for response from tailscale - check auth key")
				else:
					logging.error ("timeout waiting for response - reason unknown")

		# make changes necessary to bring connection up
		#	will fully connect if login had previously succeeded
		#	or if a valid auth key has been specified
		#	if not, a connection link is show on the UI and a manual connection will be required
		#	next get status pass will indicate that
		# call is made with a short timeout so we can monitor status
		#	but need to defer future tailscale commands until
		#	tailscale has processed the first one
		#	ALMOST any state change will signal the wait is over
		#	(status not included)

		# resetConnection attempts a new connection regardless of current state
		#	this will occur if the server name, login server or auth key change (but not at startup)
		#	or if UI triggers a logout or there is a timeout while waiting to connect
		#	there is no need to log out since a login would follow anyway
		#	and an exising connection won't survive the login
		
		# doLogout is set when the logout command is received from the UI
	
		if doLogout and backendRunning:	
			logging.info ("logging out of tailscale" )
			_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'logout' ] )
			if exitCode != 0:
				logging.error ( "tailscale logout failed " + str (exitCode) )
				logging.error (stderr)
			else:
				state = LOGGED_OUT
			doLogout = False
		if resetConnection or state == LOGGED_OUT or state == CLIENT_STOPPED:
			if resetConnection:
				resetConnection = False
				uiStateOveride = False
				if authKey == "":
					logging.info ("resetting conneciton - must reconnect manually")
				else:
					logging.info ("resetting conneciton - if auth key valid, connection will be automatic")
			## login resets the connection so don't need to send a logout
			logging.info ("logging in to tailscale as " + hostName + " server: " + loginServerUrl
							+ " key: " + authKey)
			_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'login', '--timeout=0.1s' ],
						loginServer=loginServerUrl, hostName=hostName, authKey=authKey )
			if exitCode != 0 and not "timeout" in stderr:
				logging.error ( "tailscale login failed " + str (exitCode) )
				logging.error (stderr)
			elif authKey == "":
				state = LOGIN_WAIT
			else:
				state = CONNECT_WAIT
	# end if backendRunning

	# update IP forwarding, exit-node enable - can't do until backend is running
	if state != previousState:
		# enable IP forwarding
		if ipForwardingEnabled and state == CONNECTED:
			logging.info ("IP forwarding enabled")
			enabled = '1'
			enabled2 = "true"
		# disable IP forwarding - do sysctl part ASAP
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

		# do tailscale set after backend is running
		if backendRunning:
			_, _, exitCode = sendCommand ( [ tsControlCmd, 'set', "--advertise-exit-node=" + enabled2 ] )
			if exitCode != 0:
				logging.error ( "could not change tailscale exit-node setting to " + enabled2 + " " + str (exitCode) )

	# show IP addresses only if connected
	if state == CONNECTED:
		if previousState != CONNECTED:
			logging.info ("connection successful")
		DbusService['/Ip1'] = ip1
		DbusService['/Ip2'] = ip2
		DbusService['/HostName'] = thisHostName
		DbusService['/TailnetName'] = tailnetName
		DbusService['/KeyExpiry'] = keyExpiry.split ("T")[0]
	else:
		DbusService['/Ip1'] = ""
		DbusService['/Ip2'] = ""
		DbusService['/HostName'] = ""
		DbusService['/TailnetName'] = ""
		DbusService['/KeyExpiry'] = ""
	# update dbus values regardless of state of the link
	if uiStateOveride != UNKNOWN_STATE:
		DbusService['/State'] = uiStateOveride
	elif doLogout:
		DbusService['/State'] = LOGGED_OUT
	else:
		DbusService['/State'] = state
	DbusService['/LoginLink'] = authUrl
	DbusService['/LoginServerUrl'] = loginServerUrl

	previousState = state
	#### DEBUG: enable to measure/display loop time
	## endTime = time.time ()
	## print ("main loop time %3.1f mS" % ( (endTime - startTime) * 1000 ))
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

	settingsList =	{ 'enabled': [ '/Settings/Services/Tailscale/Enabled', 0, 0, 1 ],
					  'customArguements': [ '/Settings/Services/Tailscale/CustomArguments', "", 0, 0 ],
					  'authKey' :  [ '/Settings/Services/Tailscale/AuthKey', "", 0, 0 ],
					  'loginServer': [ '/Settings/Services/Tailscale/LoginServer', "", 0, 0 ],
					}
	DbusSettings = SettingsDevice(bus=theBus, supportedSettings=settingsList,
					timeout = 30, eventCallback=None )

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

	DbusService.add_path ( '/State', 0, 0, 0 )
	DbusService.add_path ( '/Ip1', "" )
	DbusService.add_path ( '/Ip2', "" )
	DbusService.add_path ( '/HostName', "" )
	DbusService.add_path ( '/TailnetName', "" )
	DbusService.add_path ( '/KeyExpiry', "" )
	DbusService.add_path ( '/LoginLink', "" )
	DbusService.add_path ( '/LoginServerUrl', "" )

	DbusService.add_path ( '/GuiCommand', "", writeable = True )

	DbusService.register ()


	systemNameObj = theBus.get_object ("com.victronenergy.settings", "/Settings/SystemSetup/SystemName")

	# call the main loop - every 1 second
	# this section of code loops until mainloop quits
	GLib.timeout_add(1000, mainLoop)
	mainloop = GLib.MainLoop()
	mainloop.run()

	logging.critical ("TailscaleGX-control exiting")

main()

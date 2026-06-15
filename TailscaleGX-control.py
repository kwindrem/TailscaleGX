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
#		/Settings/TailscaleGX/AutoUpdateClient
#			controls automatic update of tailscale client
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
#			clientUpdate
#		/LoginServerUrl				an alternate login server (eg Headscale) ("" if using tailscale's server)
#		/KeyExpiry					time/date when auth key will expire ("" if none)
#		/TailscaleAvailableVersion	version of an available client update ("" if none)
#		/TailscaleClientVersion		version of the current tailscale client (specifically the daemon)
#		/ActiveConnections			number of active tailscale connections to this client
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
import signal
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
OFF_LINE = 12
NO_BACKEND_STATE = 13

CLIENT_UPDATING = 21
CLIENT_NO_UPDATE_NEEDED = 22
CLIENT_UPDATE_SUCCESS = 23
CLIENT_UPDATE_NO_SPACE = 28
CLIENT_UPDATE_FAIL = 29

CONNECTED = 100

INIT = 99
# state value for UI only
SERVER_ERROR = 201
CLIENT_ERROR = 202
CLIENT_TIMEOUT = 203
LOGIN_FAIL = 204

global previousState
global state
global systemNameObj
global systemName
global hostName
global loginServer
global loginServerUrl
global resetConnection
global restartBackend
global wasIpForwarding
global endTailscaleControl
global lastConnectedTime
global lastClientVersionCheckTime
global availableVersion

state = INIT
previousState = INIT
systemNameObj = None
systemName = None
hostName = None
authKey = None
lastResponseTime = 0
reportClientError = False
loginServer = None
loginServerUrl = None
resetConnection = False
restartBackend = False
doLogout = False
doClientUpdate = False
wasIpForwarding = False
endTailscaleControl = False
lastConnectedTime = 0
lastClientVersionCheckTime = 0
availableVersion = ""

def mainLoop ():
	global DbusSettings
	global DbusService
	global previousState
	global state
	global systemName
	global hostName
	global authKey
	global lastResponseTime
	global reportClientError
	global loginServer
	global loginServerUrl
	global resetConnection
	global restartBackend
	global doLogout
	global doClientUpdate
	global wasIpForwarding
	global endTailscaleControl
	global mainloop
	global lastConnectedTime
	global lastClientVersionCheckTime
	global availableVersion

	# endTailscaleControl can be set asynchronusly
	#	allow loop to run one last time from the top
	endMainLoop = endTailscaleControl

	startTime = time.time ()
	if state == INIT:
		lastResponseTime = startTime
		lastConnectedTime = startTime
		lastClientVersionCheckTime = 0

		restartBackend = False
		wasIpForwarding = False

	thisHostName = ""
	loginInfo = ""
	backendState = ""
	authUrl = ""
	ip1 = ""
	ip2 = ""
	keyExpiry = ""
	tailnetName = ""
	clientVersion = ""
	autoUpdateClientOk = False
	activeConnections = None

	# see if backend is running
	stdout, _, _ = sendCommand ( [ 'svstat', "/service/TailscaleGX-backend" ] )
	if ": up" in stdout:
		backendRunning = True
	else:
		backendRunning = False

	# endMainLoop forces tailscaleEnabled false
	#	this will disable IP forwarding and shutdown TailscaleGX-backend
	#	restoring normal network operations
	tailscaleEnabled = not endMainLoop and DbusSettings ['enabled'] == 1
	isConnected = state == CONNECTED
	wasConnected = previousState == CONNECTED
	if isConnected != wasConnected or state == INIT:
		resetForwarding = True
	else:
		resetForwarding = False
	
	ipForwarding = isConnected and tailscaleEnabled and DbusSettings ['customArguements'] == "--advertise-exit-node=true"

	if ipForwarding != wasIpForwarding or resetForwarding:
		wasIpForwarding = ipForwarding
		# enable IP forwarding
		if ipForwarding:
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
				name = re.sub(r"[!@#$%^&*()\[\]{};:,./<>?\|`'~=_+ ]", "-", name)
				name = name.replace ('\\', '-')
				# host name must start with a letter or number
				name = name.strip(' -').lower ()
				hostName = name
			logging.info ("system name: " + systemName + "  host name: " + hostName)
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
		if guiCommand == 'clientUpdate':
			logging.info ("tailscale client update command received from UI")
			doClientUpdate = True

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
			logging.info ("no auth key")
		if state != INIT:
			resetConnection = True

	# stop backend
	if restartBackend or ( not tailscaleEnabled and backendRunning ) :
		logging.info ("stopping TailscaleGX-backend")
		_, _, exitCode = sendCommand ( [ 'svc', '-d', "/service/TailscaleGX-backend"] )
		if exitCode != 0:
			logging.error ( "stop TailscaleGX failed " + str (exitCode) )
		backendRunning = False
		restartBackend = False

	# start backend
	elif tailscaleEnabled and not backendRunning and state != BACKEND_STARTING:
		logging.info ("starting TailscaleGX-backend")
		_, _, exitCode = sendCommand ( [ 'svc', '-u', "/service/TailscaleGX-backend"] )
		if exitCode != 0:
			logging.error ( "start TailscaleGX failed " + str (exitCode) )
		else:
			state = BACKEND_STARTING

	uiStateOveride = UNKNOWN_STATE
	if not backendRunning:
		if state != BACKEND_STARTING:
			state = BACKEND_NOT_RUNNING
		# prevent reporting an immediate no response when backend begins
		lastResponseTime = startTime

	# backend running - get and process status
	else:
		stdout, stderr, exitCode = sendCommand ( [ tsControlCmd, 'status', '--active=true', '--json=true' ], 
					timeout=1.0 )
		if exitCode == 124:
			state = STATUS_TIMEOUT
		elif exitCode == 0:
			try:
				status = json.loads (stdout)
				backendState = status["BackendState"]
				clientVersion = status["Version"].split ("-") [0]
				peers = status ["Peer"]
				if peers != None:
					activeConnections = len ( peers )
					if activeConnections == 0:
						autoUpdateClientOk = True
			except Exception as ex:
				logging.error ("Status message json parsing error: ", str (ex.args) )
				backendState = ""
				state = WAIT_FOR_RESPONSE
			if backendState == "NeedsLogin":
				lastResponseTime = startTime
				try:
					authUrl = status["AuthURL"]
				except: pass
				if state != CONNECT_WAIT and state != LOGIN_WAIT:
					state = LOGGED_OUT
			elif backendState == "Running":
				onLine = True	# assume on-line in case status doesn't include Online info
				try:
					# extract values from status report
					#	default values set above will prevail if unable
					# parameters are tried individually to prevent failure of one
					#	to prevent reading others
					selfBlock = status["Self"]
					try:
						thisHostName = selfBlock["HostName"]
					except: pass
					try:
						onLine = selfBlock["Online"]
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
				if onLine:
					state = CONNECTED
					lastResponseTime = startTime
					lastConnectedTime = startTime
				# reset timer if just entering connected/off-line states
				elif previousState != CONNECTED and previousState != OFF_LINE:
					lastConnectedTime = startTime
				# delay reporting off-line to cover up short dropouts
				elif startTime - lastConnectedTime < 5:
					state = CONNECTED
				else:
					state = OFF_LINE

			elif backendState == "Stopped":
				lastResponseTime = startTime
				state = CLIENT_STOPPED
			elif backendState == "Starting":
				state = CLIENT_STARTING
			elif backendState == "NoState":
				state = NO_BACKEND_STATE
			elif backendState == "InUseOtherUser":
				lastResponseTime = startTime
				state = IN_USE
			elif backendState == "NeedsMachineAuth":
				lastResponseTime = startTime
				state = MACH_AUTH
			else:
				logging.warning ("Unknown backendState " + backendState + " - ingorning")
		else:
			logging.error ("Error reading status", exitCode)
			state = WAIT_FOR_RESPONSE


		# for abnormal conditions, log and notify UI, and eventually reset the connection
		timeSinceResponse = startTime - lastResponseTime
		if state == STATUS_TIMEOUT:
			if timeSinceResponse > 5:
				uiStateOveride = CLIENT_TIMEOUT
			if timeSinceResponse > 30:
				restartBackend = True
				logging.error ("timeout waiting for response from client")
		if state == NO_BACKEND_STATE:
			if timeSinceResponse > 5:
				uiStateOveride = CLIENT_ERROR
			if timeSinceResponse > 30:
				restartBackend = True
				logging.error ("timeout waiting for client state")
		elif state == CLIENT_STARTING:
			if timeSinceResponse > 30:
				restartBackend = True
				logging.error ("timeout waiting for client to start")
		elif state == WAIT_FOR_RESPONSE:
			if timeSinceResponse > 5:
				uiStateOveride = SERVER_ERROR
			if timeSinceResponse > 30:
				resetConnection = True
				if loginServerUrl != "" and authKey != "":
					logging.error ("timeout waiting for response from tailscale login server - check URL and auth key")
				elif loginServerUrl != "":
					logging.error ("timeout waiting for response from " + loginServerUrl + " - check URL")
				elif authKey != "":
					logging.error ("timeout waiting for response from tailscale - check auth key")
				else:
					logging.error ("timeout waiting for response - reason unknown")
		elif state == LOGIN_WAIT and authUrl =="":
			if timeSinceResponse > 5:
				uiStateOveride = LOGIN_FAIL
			if timeSinceResponse > 30:
				restartBackend = True
				if loginServerUrl != "":
					logging.error ("timeout waiting for response from " + loginServerUrl )
				else:
					logging.error ("timeout waiting for response from tailscale login server")
		elif state == OFF_LINE:
			if (previousState != OFF_LINE):
				logging.info ("connection off-line" )
			if timeSinceResponse > 20:
				logging.error ("timeout waiting for on-line")
				restartBackend = True

		# bring connection up or shut it down
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

		elif resetConnection or state == LOGGED_OUT or state == CLIENT_STOPPED:
			if resetConnection:
				resetConnection = False
				logging.info ("resetting conneciton")
			logging.info ("logging in to tailscale as " + hostName + " server: " + loginServerUrl)
			if authKey == "":
				logging.info ("no auth key - must reconnect manually")
			else:
				logging.info ("resetting conneciton - if auth key valid, connection will be automatic")
				logging.info ("auth key: " + authKey)
			_, stderr, exitCode = sendCommand ( [ tsControlCmd, 'login', '--timeout=0.1s' ],
						loginServer=loginServerUrl, hostName=hostName, authKey=authKey )
			if exitCode != 0 and not "timeout" in stderr:
				logging.error ( "tailscale login failed " + str (exitCode) )
				logging.error (stderr)
			elif authKey == "":
				state = LOGIN_WAIT
			else:
				state = CONNECT_WAIT

		# this takes time (~ 0.5 sec with fast network, 5 sec of no network) so only do every minute
		#	otherwise 1 sec main loop is delayed
		if startTime > lastClientVersionCheckTime + 60:
			stdout, _, exitCode = sendCommand ( [ tsControlCmd, 'version', '--upstream', '--json=true' ],
						timeout=5 )
			if exitCode == 0:
				versionInfo = json.loads (stdout)
				availableVersion = versionInfo ["upstream"]
			else:
				availableVersion = ""
			lastClientVersionCheckTime = startTime

	# end if backendRunning

	# show IP addresses only if connected
	if state == CONNECTED:
		if previousState == OFF_LINE:
			logging.info ("connection on-line")
		elif previousState != CONNECTED:
			logging.info ("connection successful")
		DbusService['/Ip1'] = ip1
		DbusService['/Ip2'] = ip2
		DbusService['/HostName'] = thisHostName
		DbusService['/TailnetName'] = tailnetName
		DbusService['/KeyExpiry'] = keyExpiry.split ("T")[0]
		DbusService['/ActiveConnections'] = activeConnections
	else:
		DbusService['/Ip1'] = ""
		DbusService['/Ip2'] = ""
		DbusService['/HostName'] = ""
		DbusService['/TailnetName'] = ""
		DbusService['/KeyExpiry'] = ""
		DbusService['/ActiveConnections'] = None

	# update dbus values regardless of state of the link
	if uiStateOveride != UNKNOWN_STATE:
		DbusService['/State'] = uiStateOveride
	elif doLogout:
		DbusService['/State'] = LOGGED_OUT
	else:
		DbusService['/State'] = state
	DbusService['/LoginLink'] = authUrl
	DbusService['/LoginServerUrl'] = loginServerUrl

	# update current and available client versions for UI
	#	available is set to "" if it is same or older than current
	availableVersionNumber = 0
	try:
		parts = availableVersion.split (".")
		availableVersionNumber = int (parts[0]) * 1000000
		if len (parts) > 1:
			availableVersionNumber += int (parts[1]) * 1000
		if len (parts) > 2:
			availableVersionNumber += int (parts[2])
	except:
		availableVersionNumber = 0

	clientVersionNumber = 0
	try:
		parts = clientVersion.split (".")
		clientVersionNumber = int (parts[0]) * 1000000
		if len (parts) > 1:
			clientVersionNumber += int (parts[1]) * 1000
		if len (parts) > 2:
			clientVersionNumber += int (parts[2])
	except:
		clientVersionNumber = 0

	DbusService['/TailscaleClientVersion'] = clientVersion

	if backendRunning and availableVersionNumber > clientVersionNumber:
		DbusService['/TailscaleAvailableVersion'] = availableVersion

		# check for automatic client updates
		if not doClientUpdate and autoUpdateClientOk and DbusSettings['autoUpdateClient'] == 1 :
			logging.info ("automatic tailscale client update triggered")
			doClientUpdate = True
	else:
		DbusService['/TailscaleAvailableVersion'] = ""
		if doClientUpdate:
			logging.info ("tailscale client update not needed - skipping")
			doClientUpdate = False

	# update tailscale client
	#	this is done in line because the update does not return until it finishes (~5 seconds)
	#	or times out (~20 seconds)
	if doClientUpdate:
		logging.info ("updating tailscale client")
		DbusService['/State'] = CLIENT_UPDATING
		# make sure there's enough space (> 100 MB) on /data for the update
		_, _, freeSpace = shutil.disk_usage("/data")
		if freeSpace < 100 * 10**6:
				logging.warning ("tailscale client update failed - no space on /data")
				DbusService['/State'] = CLIENT_UPDATE_NO_SPACE
				if DbusSettings['autoUpdateClient'] == 1:
					logging.warning ("disabling automatic client updates")
					DbusSettings['autoUpdateClient'] = 0
				time.sleep (5)
		else:
			stdout, _, _ = sendCommand ( [ tsControlCmd, 'update', '--yes' ] ) 
			if "updated successfully" in stdout:
				logging.info ("tailscale client updated")
				DbusService['/State'] = CLIENT_UPDATE_SUCCESS
				restartBackend = True
			elif "no update needed" in stdout:
				logging.info ("tailscale client already up to date")
				DbusService['/State'] = CLIENT_NO_UPDATE_NEEDED
				time.sleep (5)
			else:
				logging.warning ("tailscale client update failed")
				DbusService['/State'] = CLIENT_UPDATE_FAIL
				time.sleep (5)
		doClientUpdate = False


	previousState = state
	#### DEBUG: enable to measure/display loop time
	## endTime = time.time ()
	## print ("main loop time %3.1f mS" % ( (endTime - startTime) * 1000 ))

	if endMainLoop:
		mainloop.quit()
		return False
	else:
		return True


# tells main loop to disable tailscale and exit

def signalTerm (signal, frame):
	global	endTailscaleControl
	endTailscaleControl = True
	logging.critical ("received TERM signal - TailscaleGX-control shutting down")

signal.signal (signal.SIGTERM, signalTerm)


def main():
	global DbusSettings
	global DbusService
	global systemNameObj
	global mainloop

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
					  'autoUpdateClient': [ '/Settings/Services/Tailscale/AutoUpdateClient', 0, 0, 1 ],
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
	DbusService.add_path ( '/TailscaleClientVersion', "" )
	DbusService.add_path ( '/TailscaleAvailableVersion', "" )
	DbusService.add_path ( '/ActiveConnections', 0, 0, 0 )
	

	DbusService.add_path ( '/GuiCommand', "", writeable = True )

	DbusService.register ()

	systemNameObj = theBus.get_object ("com.victronenergy.settings", "/Settings/SystemSetup/SystemName")

	# call the main loop - every 1 second
	# this section of code loops until mainloop quits
	GLib.timeout_add(1000, mainLoop)
	mainloop = GLib.MainLoop()
	mainloop.run()

	logging.info ("TailscaleGX-control exiting")
	logging.info ("tailscale remote connections no longer available")

main()

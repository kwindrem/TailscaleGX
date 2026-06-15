/////// new menu for Tailscale GX

import QtQuick 1.1
import "utils.js" as Utils
import com.victron.velib 1.0

MbPage
{
	property string servicePrefix: "com.victronenergy.tailscaleGX"
	property string settingsPrefix: "com.victronenergy.settings/Settings/Services/Tailscale"

	id: root
	title: qsTr("Remote access (tailscale) setup")
	VBusItem { id: clientStateItem; bind: Utils.path(servicePrefix, "/State") }
	VBusItem { id: loginItem; bind: Utils.path(servicePrefix, "/LoginLink") }
	VBusItem { id: ip1Item; bind: Utils.path(servicePrefix, "/Ip1") }
	VBusItem { id: ip2Item; bind: Utils.path(servicePrefix, "/Ip2") }
	VBusItem { id: hostNameItem; bind: Utils.path(servicePrefix, "/HostName") }
	VBusItem { id: tailnetNameItem; bind: Utils.path(servicePrefix, "/TailnetName") }
	VBusItem { id: keyExpiryItem; bind: Utils.path(servicePrefix, "/KeyExpiry") }
	VBusItem { id: commandItem; bind: Utils.path(servicePrefix, "/GuiCommand") }
	VBusItem { id: enabledItem; bind: Utils.path(settingsPrefix, "/Enabled") }
	VBusItem { id: customArgumentsItem; bind: Utils.path(settingsPrefix, "/CustomArguments") }
	VBusItem { id: clientVersionItem; bind: Utils.path(servicePrefix, "/TailscaleClientVersion") }
	VBusItem { id: availableVersionItem; bind: Utils.path(servicePrefix, "/TailscaleAvailableVersion") }
	property string availableVersion: availableVersionItem.valid ? availableVersionItem.value : ""
	VBusItem { id: activeConnectionItem; bind: Utils.path(servicePrefix, "/ActiveConnections") }

	property int clientState: clientStateItem.valid ? clientStateItem.value : 0
	property string ip1: ip1Item.valid ? ip1Item.value : ""
	property string ip2: ip2Item.valid ? ip2Item.value : ""
	property string hostName: hostNameItem.valid ? hostNameItem.value : ""
	property string tailnetName: tailnetNameItem.valid ? tailnetNameItem.value : ""
	property string keyExpiry: keyExpiryItem.valid ? keyExpiryItem.value : ""
	property string loginLink: loginItem.valid ? loginItem.value : ""
	
	property bool isRunning: clientStateItem.valid
	property bool isEnabled: enable.checked && isRunning
	property bool isConnected: clientState == 100 && isEnabled	// CONNECTED

	VBusItem { id: authKeyItem; bind: Utils.path(settingsPrefix, "/AuthKey") }
	property string authKey: authKeyItem.valid ? authKeyItem.value : ""
	property string joinedKey: keyPt1.item.value + keyPt2.item.value + keyPt3.item.value

	VBusItem { id: loginServerUrlItem; bind: Utils.path(servicePrefix, "/LoginServerUrl") }
	property string loginServerUrl: loginServerUrlItem.valid ? loginServerUrlItem.value : ""

	function getExpiry ()
	{
		if ( keyExpiry != "" && authKey != "")
			return ( "\n" + qsTr ("node key expires: ") + keyExpiry + qsTr ("  auth key expires: ?") )
		else if (keyExpiry != "")
			return ( "\n" + qsTr ("expires: ") + keyExpiry )
		else if (authKey != "")
			return ( "\n" + qsTr ("  auth key expires: ?") )
		else
			return ( "" )
	}

	function getActiveConnections ()
	{
		if ( ! activeConnectionItem.valid )
			return ( "\n" + qsTr ("active connections: ?") )
		else
			return ( "\n" + qsTr ("active connections: ") + activeConnectionItem.value )
	}
	
	function getState ()
	{
		if ( ! isEnabled )
			return qsTr ("remote connections not accepted\n(disabled above)")
		else if ( ! isRunning )
			return qsTr ("TailscaleGX control not running")
		else if (clientState == 12)	// OFF_LINE
			return ( qsTr ("tailscale connection off line\ncheck internet connection") )
		else if ( isConnected )	// clientState == CONNECTED && isEnabled
			return ( qsTr ("accepting remote connections at:\n")
					+ hostName + "\n" + ip1 + "\n" + ip2
					+ getActiveConnections () + getExpiry () )
		else if ( clientState == 1 || clientState == 2)	// BACKEND_STARTING || BACKEND_NOT_RUNNING
			return qsTr ("TailscaleGX starting ...")
		else if ( clientState == 3)	// CLIENT_STOPPED
			return qsTr ("tailscale client stopped")
		else if ( clientState == 4)	// LOGGED_OUT
			return qsTr ("this GX device is logged out of tailscale")
		else if ( clientState == 5 || ( clientState == 6 ) )	// WAIT_FOR_RESPONSE || CONNECT_WAIT
		{
			if (loginServerUrl == "")
				return qsTr ("waiting for response from tailscale server")
			else
				return qsTr ("waiting for response from login server\n" + loginServerUrl)
		}
		else if (clientState == 9)	// LOGIN_WAIT
		{
			if (loginLink == "")
			{
				if (loginServerUrl == "")
					return qsTr ("waiting for response from tailscale server")
				else
					return qsTr ("waiting for response from login server\n" + loginServerUrl)
			}
			else
				return ( qsTr ("connect this GX device to your account at:\n\n") + loginLink)
		}
		else if (clientState == 7 || clientState == 13)	// STATUS_TIMEOUT || NO_BACKEND_STATE
			return ( qsTr ("waiting for response from tailscale client") )
		else if (clientState == 8)	// CLIENT_STARTING
			return ( qsTr ("logging in to server ...") )
		else if ( clientState == 201 )	// SERVER_ERROR
		{
			if (loginServerUrl != "" && authKey != "")
				return ( qsTr ("tailscale server not responding\ncheck internet connetion\login server URL and auth key") )
			else if (loginServerUrl != "")
				return ( qsTr ("tailscale server not responding\ncheck internet connetion\and login server URL") )
			else if (authKey != "")
				return ( qsTr ("tailscale server not responding\ncheck internet connetion\ and auth key"))
			else
				return ( qsTr ("tailscale server not responding\ncheck internet connetion"))
		}
		else if ( clientState == 202 )	// CLIENT_ERROR
			return ( qsTr ("tailscale client can't connect\ncheck internet connection") )
		else if ( clientState == 203 )	// CLIENT_TIMEOUT
			return ( qsTr ("tailscale client not responding") )
		else if ( clientState == 204 )	// LOGIN_FAIL
		{
			if (loginServerUrl != "")
				return ( qsTr ("login server timeout\ncheck login server URL\n") + loginServerUrl + qsTr ("\nor internet connection") )
			else
				return ( qsTr ("tailscale login server timeout\ncheck internet connection"))
		}
		else if ( clientState == 99 )	// INIT
			return qsTr (" Tailscale control initializing")
		else if ( clientState == 10 )	// IN_USE
			return ( qsTr ("can not connect\nmay be connected to another tailnet") )
		else if ( clientState == 11 )	// MACH_AUTH
			return ( qsTr ("needs authorization\nvisit server admin console") )
		else if ( clientState == 0 )	// UNKNOWN_STATE
			return ""

		else if ( clientState == 21 )	// CLIENT_UPDATING
			return qsTr ("Updating tailscale client ...")
		else if ( clientState == 22 )	// CLIENT_NO_UPDATE_NEEDED
			return qsTr ("tailscale client already up to date")
		else if ( clientState == 23 )	// CLIENT_UPDATE_SUCCESS
			return qsTr ("tailscale client updated")
		else if ( clientState == 28 )	// CLIENT_UPDATE_NO_SPACE
			return qsTr ("tailscale client update FAILED - no space on /data")
		else if ( clientState == 29 )	// CLIENT_UPDATE_FAIL
			return qsTr ("tailscale client update FAILED - check network")

		else
			return ( qsTr ( "unknown state " ) + clientState )
	}
	
    model: VisibleItemModel
	{
		MbSwitch
		{
			id: enable
			name: qsTr("Allow secure remote connections via tailscale")
			bind: Utils.path( settingsPrefix, "/Enabled")
			writeAccessLevel: User.AccessInstaller
			show: isRunning
		}
		MbItemText
		{
			text: getState ()
			wrapMode: Text.WordWrap
			horizontalAlignment: Text.AlignHCenter
		}
		MbOK
		{
			id: logoutButton
			description: qsTr("Account: ") + ( tailnetName == "" ? qsTr ("(unknown)") : tailnetName )
			value: qsTr ("Logout")
			onClicked: commandItem.setValue ('logout')
			writeAccessLevel: User.AccessInstaller
			show: isConnected
		}
		MbOK
		{
			id: clientUpdateButton
			description: qsTr("Tailscale client version: ") + ( clientVersionItem.value )
			value: availableVersion != "" ? qsTr ("Update to " + availableVersion) : qsTr ("no update available")
			onClicked: commandItem.setValue ('clientUpdate')
			writeAccessLevel: User.AccessInstaller
			show: isEnabled && clientVersionItem.value != "" && clientState != 21	// CLIENT_UPDATING
		}
		MbSwitch
		{
			id: clientAutoUpdate
			name: qsTr("Automatically update tailscale client")
			bind: Utils.path( settingsPrefix, "/AutoUpdateClient")
			writeAccessLevel: User.AccessInstaller
			show: isEnabled
		}
		MbSwitch
		{
			id: ipForwardEnable
			name: qsTr("IP forwarding")
			bind: Utils.path( settingsPrefix, "/CustomArguments")
			valueTrue: "--advertise-exit-node=true"
			valueFalse: ""
			writeAccessLevel: User.AccessInstaller
			show: isEnabled
		}
		MbEditBox
		{
			id: loginServer
			description: "Alternate Login Server URL"
			showAccessLevel: User.AccessInstaller
			maximumLength: 50
			item.bind: Utils.path(settingsPrefix, "/LoginServer")
			show: isEnabled
		}
		MbItemText
		{
			text: qsTr ("Tailscale authorization key:\n") + joinedKey + qsTr ("\nenter below in up to three parts")
			wrapMode: Text.WrapAnywhere
			show: isEnabled
		}
		
		MbEditBox
		{
			id: keyPt1
			description: "auth key part 1"
			showAccessLevel: User.AccessInstaller
			maximumLength: 25
			item.value: authKey.substring (0, 25)
			onEditDone: authKeyItem.setValue (joinedKey)
			show: isEnabled
		}
		MbEditBox
		{
			id: keyPt2
			description: "auth key part 2"
			showAccessLevel: User.AccessInstaller
			maximumLength: 25
			item.value: authKey.substring (25, 50)
			onEditDone: authKeyItem.setValue (joinedKey)
			show: isEnabled
		}
		MbEditBox
		{
			id: keyPt3
			description: "auth key part 3"
			showAccessLevel: User.AccessInstaller
			maximumLength: 25
			item.value: authKey.substring (50)
			onEditDone: authKeyItem.setValue (joinedKey)
			show: isEnabled
		}
	}
}

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
	VBusItem { id: stateItem; bind: Utils.path(servicePrefix, "/State") }
	VBusItem { id: loginItem; bind: Utils.path(servicePrefix, "/LoginLink") }
	VBusItem { id: ip1Item; bind: Utils.path(servicePrefix, "/Ip1") }
	VBusItem { id: ip2Item; bind: Utils.path(servicePrefix, "/Ip2") }
	VBusItem { id: hostNameItem; bind: Utils.path(servicePrefix, "/HostName") }
	VBusItem { id: tailnetNameItem; bind: Utils.path(servicePrefix, "/TailnetName") }
	VBusItem { id: keyExpiryItem; bind: Utils.path(servicePrefix, "/KeyExpiry") }
	VBusItem { id: commandItem; bind: Utils.path(servicePrefix, "/GuiCommand") }
	VBusItem { id: enabledItem; bind: Utils.path(settingsPrefix, "/Enabled") }
	VBusItem { id: customArgumentsItem; bind: Utils.path(settingsPrefix, "/CustomArguments") }

	property int state: stateItem.valid ? stateItem.value : 0
	property string ip1: ip1Item.valid ? ip1Item.value : ""
	property string ip2: ip2Item.valid ? ip2Item.value : ""
	property string hostName: hostNameItem.valid ? hostNameItem.value : ""
	property string tailnetName: tailnetNameItem.valid ? tailnetNameItem.value : ""
	property string keyExpiry: keyExpiryItem.valid ? keyExpiryItem.value : ""
	property string loginLink: loginItem.valid ? loginItem.value : ""
	
	property bool isRunning: stateItem.valid
	property bool isEnabled: enable.checked
	property bool isConnected: state == 100 && isEnabled	// CONNECTED

	VBusItem { id: authKeyItem; bind: Utils.path(settingsPrefix, "/AuthKey") }
	property string authKey: authKeyItem.valid ? authKeyItem.value : ""
	property string joinedKey: keyPt1.item.value + keyPt2.item.value + keyPt3.item.value

	VBusItem { id: loginServerUrlItem; bind: Utils.path(servicePrefix, "/LoginServerUrl") }
	property string loginServerUrl: loginServerUrlItem.valid ? loginServerUrlItem.value : ""

	function getExpiry ()
	{
		if ( keyExpiry != "" && authKey != "")
			return ( qsTr ("node key expires: ") + keyExpiry + qsTr ("  auth key expires: ?") )
		else if (keyExpiry != "")
			return ( qsTr ("expires: ") + keyExpiry )
		else if (authKey != "")
			return ( qsTr ("  auth key expires: ?") )
		else
			return ( "" )
	}
	
	function getState ()
	{
		if ( ! isEnabled )
			return qsTr ("remote connections not accepted\n(disabled above)")
		else if ( ! isRunning )
			return qsTr ("TailscaleGX control not running")
		else if (state == 12)	// NETWORK_DOWN
			return ( qsTr ("login server not reachable - check")
			+ ( loginServerUrl != "" ? ( qsTr ("\nlogin server URL: ") + loginServerUrl ) : "" ) 
			+ qsTr ("\nand internet connection") )
		else if ( isConnected )	// state == CONNECTED && isEnabled
			return ( qsTr ("accepting remote connections at:\n")
					+ hostName + "\n" + ip1 + "\n" + ip2 + "\n" + getExpiry () )
		else if ( state == 1 || state == 2)	// BACKEND_STARTING || BACKEND_NOT_RUNNING
			return qsTr ("TailscaleGX starting ...")
		else if ( state == 3)	// CLIENT_STOPPED
			return qsTr ("tailscale client stopped")
		else if ( state == 4)	// LOGGED_OUT
			return qsTr ("this GX device is logged out of tailscale")
		else if ( state == 5 || ( state == 6 ) )	// WAIT_FOR_RESPONSE || CONNECT_WAIT
		{
			if (loginServerUrl == "")
				return qsTr ("waiting for a response from tailscale server")
			else
				return qsTr ("waiting for a response from login server\n" + loginServerUrl)
		}
		else if (state == 9)	// LOGIN_WAIT
				return ( qsTr ("connect this GX device to your account at:\n\n") + loginLink)
		else if (state == 7)	// STATUS_TIMEOUT
			return ( qsTr ("waiting for response from tailscale client") )
		else if (state == 8)	// CLIENT_STARTING
			return ( qsTr ("logging in to server ...") )
		else if ( state == 201 )	// SERVER_ERROR
		{
			if (loginServerUrl != "" && authKey != "")
				return ( qsTr ("server timeout - check login server URL and auth key") )
			else if (loginServerUrl != "")
				return ( qsTr ("server timeout - check login server URL") )
			else if (authKey != "")
				return ( qsTr ("server timeout - check auth key"))
			else
				return ( qsTr ("server timeout"))
		}
		else if ( state == 202 )	// CLIENT_ERROR
			return ( qsTr ("tailscale client not responding") )
		else if ( state == 99 )	// INIT
			return qsTr (" Tailscale control initializing")
		else if ( state == 10 )	// IN_USE
			return ( qsTr ("can not connect\nmay be connected to another tailnet") )
		else if ( state == 11 )	// MACH_AUTH
			return ( qsTr ("needs authorization\nvisit server admin console") )
		else if ( state == 0 )	// UNKNOWN_STATE
			return ""
		else
			return ( qsTr ( "unknown state " ) + state )
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

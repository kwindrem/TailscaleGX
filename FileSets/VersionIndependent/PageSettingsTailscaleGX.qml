/////// new menu for Tailscale GX

import QtQuick 1.1
import "utils.js" as Utils
import com.victron.velib 1.0

MbPage
{
	property string servicePrefix: "com.victronenergy.tailscaleGX"
	property string settingsPrefix: "com.victronenergy.settings/Settings/TailscaleGX"

	id: root
	title: qsTr("Remote access (tailscale) setup")
	VBusItem { id: stateItem; bind: Utils.path(servicePrefix, "/State") }
	VBusItem { id: loginItem; bind: Utils.path(servicePrefix, "/LoginLink") }
	VBusItem { id: ipV4Item; bind: Utils.path(servicePrefix, "/IPv4") }
	VBusItem { id: ipV6Item; bind: Utils.path(servicePrefix, "/IPv6") }
	VBusItem { id: hostNameItem; bind: Utils.path(servicePrefix, "/HostName") }
	VBusItem { id: commandItem; bind: Utils.path(servicePrefix, "/GuiCommand") }
	VBusItem { id: enabledItem; bind: Utils.path(settingsPrefix, "/Enabled") }
	VBusItem { id: ipForwardingItem; bind: Utils.path(settingsPrefix, "/IpForwarding") }

	property int connectState: stateItem.valid ? stateItem.value : 0
	property string ipV4: ipV4Item.valid ? ipV4Item.value : ""
	property string ipV6: ipV6Item.valid ? ipV6Item.value : ""
	property string hostName: hostNameItem.valid ? hostNameItem.value : ""
	property string loginLink: loginItem.valid ? loginItem.value : ""
	
	property bool isRunning: stateItem.valid
	property bool isEnabled: enable.checked && isRunning
	property bool isConnected: connectState == 100 && isEnabled

	function getState ()
	{
		if ( ! isRunning )
			return qsTr ( "TailscaleGX control not running" )
		else if ( ! isEnabled )
			return qsTr ( "remote connections not accepted\n (disabled above)" )
		else if ( isConnected )
			return ( qsTr ( "accepting remote connections at:\n")
					+ hostName + "\n" + ipV4 + "\n" + ipV6 )
		else if ( connectState == 0 )
			return ""
		else if ( connectState == 1 )
			return qsTr ("starting ...")
		else if ( connectState == 2 || connectState == 3)
			return qsTr ("tailscale starting ...")
		else if ( connectState == 4)
			return qsTr ("this GX device is logged out of tailscale")
		else if ( connectState == 5)
			return qsTr ("waiting for a response from tailscale ...")
		else if ( connectState == 6)
			return ( qsTr ("connect this GX device to your tailscale account at:\n\n") + loginLink )
		else
			return ( qsTr ( "unknown state " ) + connectState )
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
		MbSwitch
		{
			id: ipForwardEnable
			name: qsTr("IP forwarding")
			bind: Utils.path( settingsPrefix, "/IpForwarding")
			writeAccessLevel: User.AccessInstaller
			show: isEnabled
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
			description: qsTr("Disconnect from tailscale account")
			value: qsTr ("Logout")
			onClicked: commandItem.setValue ('logout')
			
			writeAccessLevel: User.AccessInstaller
			show: isConnected
		}
	//// add detailed instructions	
	}
}

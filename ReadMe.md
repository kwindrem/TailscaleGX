# TailscaleGX

This package is adds the Tailscale VPN software including a user interface to Victron GX devices.

Tailscale provides a VPN-like connection for virtually any device.

Victron VRM provides access to the GX device's GUI,
but not a command line interface to the GX devie.
TailscaleGX provides an ssh connection and also http access to all the GUIs available on the GX device
Any web browser or ssh tool (ssh, scp, rsync, etc.) can be used to communicate with the GX device.
However a tailscale account is required and the tailscale app must be installed on the computer,
tablet or smart phone connecting to the GX device.

The GX device must also be logged in to the SAME tailscale account.

tailscale clients are available for Windows, Mac OS, iOS, Linux and Android.

TailscaleGX is on GitHub at https://github.com/kwindrem/TailscaleGX

And more information is available at:

https://tailscale.com

TailscaleReadMe.md file is also included in this package.

# NOTE

Victron Energy has tabled a native tailscale implementation due to security concerns.

TailscaleGX will continue to provide tailscale support for those that understand and accept the security risks.

TailscaleGX configuration is through the Classic UI only (aka gui-v1).
No work is planned to support tailscale configuraiton via the New UI(aka gui-v2).
Although it is also possible to confiture it via a combination of
the command line (running /data/TailscaleGX/tailscale) and dbus-spy (to turn tailscale on and off).

# NOTE
Support for firmware prior to v3.10 has been dropped starting with TailScaleGX v1.6

If you are running older versions, change the branch/tag to preV3.10support
	for any packages you wish to run on that firmware


# Using

ssh access does NOT need to be enabled for ssh access via tailscale !
However you may need to define a root password or enable ssh keys
to complete the login.
To do this refer to:

https://www.victronenergy.com/live/ccgx:root_access

After installing TailscaleGX,
navigate to __Settings / General / Remote access via tailscale__

and turn on __Allow remote connections__

After tailscale starts up you will be presented a message reading:

>__connect this GX devices to your account at:__

>__https://login.tailscale.com/x/xxxxxxxxxxxxx__

On a computer, tablet or smart phone with the tailscale app installed,
enter the URL exactly as it is shown on the screen.

You will be asked login to your tailscale account.

Press the __Connect__ button.

On the GX devive, the message should change to:

>__accepting remote connections at:__

>__xxx.xxx.xxx.xxx__

>__xxxx:xxxx:xxxx::xxxx:xxxx__

(IPv4 and IPv6 addresses)

You can then connect to the GX device from any computer, etc logged in to your tailscale account. 

Any tool for ssh, scp, etc or any web browser should work,
however you must have the tailscale app enabled and logged in to your account.

You can disable tailscale by turning __Allow remote connections__ off. 
Turning it on again you will reconnect to tailscale without logging in again.
The same IP addresses will be used until you logout the GX device.

If you wish to disconnect the GX device from the existing tailscale account,
press the __Logout__ button. You can then log into a different account.

Optional Authorization key and Alternate server may also be specified.
These are described in more detail below.

## tailscale update

TailscaleGX includes a stripped down tailscacle binary in order to save space.
Some functionality is left out however, for example, logging.
Also, tailscale may receive an update that is not included in the latest TailscaleGX.

The Tailscale menu provides a mechanism to update to the lates FULL binary set
if one is available.

Note that the stripped down binary is about 35 MB. About 100 MB of free space on the /data partition isneeded
to update and this may not be available on all platforms. NO CHECKS FOR AVAILABLE SPACE IS NEEDED.

Downloading TailscaleGX will overwrite an update to the FULL, latest version so you would need to reapply it.
You can also use the download to return to the stripped down version.


## Setup aids

There are several tasks required to establish a tailscale connection
that may be difficult when using the GX device UI:

1. The login URL displayed on the GX device UI must be entered into a web browser.

2. The optional auth key is very long and broken into 3 25-character entry fields in the UI.

3. An optinoal alternate login server URL could also be long

__authorizeTailscale__ is a shell script that can be run on the GX device via ssh
that may simplify these tasks.

1. The script prints the login URL which can be selected, copied and pasted into a web browser.

2. The auth key can be copied from the tailscale key generator dialog then pasted when the script is asking for a new key.

3. The same mechanism can be used for an alternate login server, or simply typed in using a keyboard

In addition to this script, you may be able to use a cell phone or tablet camera to capture the login URL
from the GX device screen. You may then be able to have it converted to text while pasting into an app.
I tested this on an iPhone 16 running iOS 18, pasting into Notes.
Selecting the text and copy/pasting into Safari successfully brought up the connect page.

# Troubleshooting

Prompts on the UI may help to isolate issues with a connection.

If for some re


# DNS issue

I experienced a one-time issue with DNS resolution failures.
I discovered a corrupted /etc/resolv.conf.
tailscaled modifies this file at connection startup and restores on connection shutdown
and it is possible a tailscaled (TailscaleGX-backend) crash resulted in the corruption.

v2.7 checks for network connection which will fail if this corruption occurs.
A login server unreachable message is displayed on the UI and "login server is NOT responding"
message is shown in the log.

The solution is to reinstall venus OS. Do this by switching the the backup firmware then using
an online install to update to the current version.

# IP Forwarding

You may optionally share the tailnet connection with other devices on your local network.

To do so, turn on IP forwarding in the Tailscale GX setup menu.

Note that IP forwarding will impact CPU performance so use with caution.

# Other tailscale enhancements

It is possible to customize tailscale via it's command line interface.
All those parameters are stored in the tailscale config which is located
in an area of the file system that survives a firmware update so thise settings would be nonvolatile.

E.g.,:

>__/data/TailscaleGX/tailscale set --advertise-routes "192.168.8.0/24"__


# Authorization key

An alternate way to connect the GX device is to use an authorization key.

This key is generated under settings in your tailscale admin console.
It then must be entered into the GX device.

The complete key is longer than supported by the GUI edit box
so it is split into up to three separate pieces for entry.
The complete code is shown above the three editable parts.
Each part is limited to 25 characters.

If you have command line access to the GX device, it is far easier to use
dbus-spy to enter the key into

> com.victronenergy.settings /Settings/Services/Tailscale/AuthKey

Or use the command line interface:

> dbus -y com.victronenergy.settings /Settings/Services/Tailscale/AuthKey SetValue [key]

# Key expiration

When creating an authorization key you must specify an expiration period (1 - 90 days).
After an auth key expires,the GX device will remain connected but if logged out, a login will fail.
So the longest lasting conneciton when using an auth key is 90 day !!

A conneciton also has a "node key" expiration of 180 days. When a node key expires, the GX device *may*
disconnect. If no valid auth key is active, the GX device will remain logged out
and will need to repeat the login process described above from the GX device.
You will not be able to connect via tailscale.

Node key expiry can be disabled in the tailscale admin console.

Node key expiry is displayed in the __accepting connections__ message if it has not been disabld

Auth key expiry is **not** shown. Suggest setting a calendar appointment to generate a new auth key
before the existing one expires and install the new one on the GX device.
So you do not loose remote connections.

For a connection that will persist forever, do not use an auth key and disable key expiry

Note that if you log out the GX device and do not have an auth key set, you will need to log back in
even if the node key has not expired.


# Alternate login server

It possible to use the tailscale client with an alternate login server
otherwise know as a Custom Control Server.

https://tailscale.com/kb/1507/custom-control-server

Headscale is one such server https://headscale.net

To switch from tailscale's 'tailnet' you simply specify the URL of the alternate server in
__Alternate Login Server URL__ via the GX device's UI

If you do not specify http:// or https://, the latter is appended to what is entered.

Refer to documentaion provided with the alternate server for how to set things up,
how to connect to it and how to an generate authorization key if one is used.

The alternate login server may support authorization keys.
If so, they the key be entered as described above

Use of an alternate login server is not guaranteed to work with TailscaleGX.

# Installing

TailscaleGX can be installed from Package manager.

In __Inactive packages__

If TailscaleGX is already in the list, select it and tap __Proceed__

If not in the list, select __new__ and fill in the details:

Packagename: TailscaleGX

GitHub user: kwindrem

GitHub branch or tag: latest

then tap __Proceed__

# Security

Only a computer, tablet or smart phone running the tailscale app
AND logged into the same account used when connecting the GX device
to tailscale can access the GX device.

There is information on the tailscale web site that discusses the security issues.

The GX device will not allow tailscale connections
when __Allow remote connections__ is turned off.

# TailscaleGX details

The tailscale included in TailscaleGX is an "extra-small" build based on
the latest stable tailscale the last time TailscaleGX was updated.
This build is about 35 MB compared to about 60 MB for the pre-built binairies.

tailscale runs as a daemon (tailscaled). 

In Venus OS, tailscaled is run as a daemontools service: __TailscaleGX-backend__

In addition a command-line application (tailscale) controls tailscaled.

The daemon only runs when __Allow remote connections__ is turned on.

A second service __TailscaleGX-control__:

- starts and stops TailscaleGX-backend
- manages bringing up the GX to tailscale server link
- collects login and connection status from tailscale
- provides this status to the GUI
- prompts the user for necessary steps to establish a connection






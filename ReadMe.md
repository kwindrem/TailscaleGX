# TailscaleGX

This package is a user interface for tailscale on Victron Energy GX devices.

tailscale provides is a VPN-like connection for virtually any device.

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

tailscale is being added to Venus OS.
When a stock tailscale is detected, TailscaleGX will not run to avoid conflics
The firmware version that will include tailscale has not been determined so the normal
obsolete version mechamism is not used at the moment but will be added when the version is known.

# NOTE
Support for firmware prior to v3.10 has been dropped starting with TailScaleGX v1.6

If you are running older versions, change the branch/tag to preV3.10support
	for any packages you wish to run on that firmware


# Using

ssh access must be enabled in Settings / General, and a root password set
or any ssh tool will not be able to access the GX device.
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

# IP Forwarding

You may optionally share the tailnet connection with other devices on your local network.

To do so, turn on IP forwarding in the Tailscale GX setup menu.

Note that IP forwarding will impact CPU performance so use with caution.

# Tailscale authorization key

An alternate way to connect the GX device to your tailnet is to use an authorization key.

This key is generated under settings in your tailscale admin console.
It then must be entered into the GX device.

The complete key is longer than supported by the GUI edit box
so it is split into up to three separate pieces for entry.
The complete code is shown above the three editable parts.
Each part is limited to 25 characters.

If you have console access to the GX device, it is far easier to use
dbus-spy to enter the key into

> com.victronenergy.settings /Settings/Services/Tailscale/AuthKey

Or use the command line interface:

> dbus -y com.victronenergy.settings /Settings/Services/Tailscale/AuthKey SetValue [key]

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

The tailscale included in TailscaleGX is an "extra-small" build of v1.70.
This build is about 25 MB compared to about 50 MB for the pre-built binairies.

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

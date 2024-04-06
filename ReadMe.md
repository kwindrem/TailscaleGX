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

The tailscale included in TailscaleGX is an "extra-small" build of v1.62.1.
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

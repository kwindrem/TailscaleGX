# TailscaleGX

NOTE: this package is still in beta and may contain bugs.
Please isntall on GX devices that you has native ssh access set up so that you can recover should there be a problem
ssh access also allows getting to logs which is essential to track down bugs.

This package is a user interface for tailscale on Victron Energy GX devices.

tailscale provices is a VPN-like connection for virtually any device.

Victron VRM provides access to the GX device's GUI,
but not a command line interface to the GX devie.
TailscaleGX provides an ssh connection and also http access to all the GUIs available on the GX device.

Please visit:

https://tailscale.com

to learn more about tailscale and to set up an account.

There is also more information in the TailscaleReadMe.md file included in this package.

A tailscale account is required to complete the connection
While you are free to used your favorite web browser or ssh tool (ssh, scp, rsync, etc.)
you need to be logged into your tailscale account on the device requesting the connection
to the GX device. 

You will need a tailscale account and tailscale client software
running on any device you wish to connect to the GX device.
Clients are available for Windows, Mac OS, iOS, Linux and Android.

TailscaleGX is on GitHub at https://github.com/kwindrem/TailscaleGX



# Using

After installing TailscaleGX,
navigate to the Settings / General / Remote Access menu
and turn on Enable remote connection.

After tailscale starts up you will be presented a message reading:
:connect this GX devices to your account at:
and a URL: https://login.tailscale.com/x/xxxxxxxxxxxxx
the part after tailscale.com will be different.

On a computer, tablet or smart phone with the tailscale app installed,
enter the URL exactly as it is shown on the screen.

You will be asked to verify your login, then a Connect button will be shown.

Tap on that.

On the GX devive, the message shoudl change to:

accepting remote connections at:

followed by an IP V4 and IP V6 address

You can then connect in to the GX device from any computer, etc logged in to the tailscale account you had active
when you followed the URL. 

You can use any unix shell for ssh, scp, etc or any web browser,
however you must have the tailscale app enabled and logged in to your account.

You can disable tailscale by turning Enable remote connection off. 

When you turn it on again you will be reconnected to tailscale
with the same IP addresses presented initially.

If you wish to disconnect the GX device from the existing tailscale account,
press the Logout button. You can then log into a different account.

# Installing

TailscaleGX can be installed from Package manager:

Go to inactive packages and if TailscaleGX is not in the list
select new to add it manually:
Packagename: TailscaleGX
GitHub user: kwindrem
GitHub branch or tag: latest

# Security

Only a computer, tablet or smart phone running the tailscale app
AND logged into the same account used when connecting the GX device
to tailscale can access the GX device.

There is information on the tailscale web site that discusses the security issues.

The GX device will not allow tailscale connections when Enable remote access is turned off.

# tailscale details

tailscale was built from v1.62.1, the most recent stable build at the time,
rather than using an available binary in order to save space.

tailscale runs as both a daemon and a control appliciton, in this case
a command line interface.

The daemon only runs when Enable remote connection is turned on.

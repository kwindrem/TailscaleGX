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


## Using

## Installing

TailscaleGX can be installed from Package manager:

Go to inactive packages and if TailscaleGX is not in the list
select new to add it manually:
Packagename: TailscaleGX
GitHub user: kwindrem
GitHub branch or tag: latest

TailscaleGX is on GitHub at 

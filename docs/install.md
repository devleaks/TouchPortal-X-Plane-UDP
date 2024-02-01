# Installation and Tests

The following steps will install Touch Portal X-Plane UDP plugin and ensure
it is working properly.

The packaged release incudes a working set of demonstration
files that works with X-Plane stock Cessna C172 aircraft.

1. Enable UDP access in X-Plane.
1. In Touch Portal, import the `TouchPortal-X-Plane-UDP_vX.Y_???.tpp` plugin corresponding to your operating system (`???`) and found in the Releases of this repository.
1. In Touch Portal, create a value named pagepath.
1. In Touch Portal, import the event `Page-Switch.tpe`.
1. In Touch Portal, import the `X-Plane Demo Page.tpz2`


# Enable UDP access in X-Plane

In X-Plane network settings, ensure that X-Plane UDP is set up and permitted.


# Import the Plugin in Touch Portal

In Touch Portal, import the plugin file `TouchPortal-X-Plane-UDP_vX.Y_???.tpp` corresponding to your operating system (`???`).

You DO need the "Pro" version of Touch Portal to be able to import plugins.


The plugin contains a sample `states.json`. file used for the demonstration.

After importing, the plugin should start immediately.

Check the log of Touch Portal to see the plugin verbose output.



# Create Page Change Help

## Create Page Path value

In Touch Portal, create a value called `pagepath` (internal name).
DO NOT change the internal name.

![Page Path value](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/page-path-value.png?raw=true)


## Import or Create Switch Page Event

In Touch Portal, create a global event called Switch Page.
You can create it, or import the `Page-Switch.tpe` file.

![Page Switch Event](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/page-switch-event.png?raw=true)


# Import the Demonstration Page

In Touch Portal, import the demonstration file `X-Plane Demo Page.tpz2`.


# Tests

You may be requested to start Touch Portal for the above action to take effect.

After restarting Touch Portal, have a look at the Touch Portal log page to check if the TouchPortal-Xplane-UDP plugin started.

On your Touch Portal client device, open the X-Plane Demo Page.

Test all features on the demo page, except the Fire Test button.

- Show map, MHz+, and MHz- buttons exercise the simple execution of command.
- The radio frequency display, its color, exercise behavior changes when X-Plane dataref values change.
- The "Strobe light" button exercises the "Set Dataref" command and changes the appearance of the button accordingly.

With the above, you have an example of each tool available through the swiss army knife TouchPortal-Xplane-UDP plugin.

No more. No less.


Finally,

- The Fire Test command exercises the long-press command (press and maintain).

But for this command to work, you will need a little extra X-Plane plugin.

Read on.



# Optional Installation for "Long Commands"

X-Plane UDP API does not accept long press commands (X-Plane commands that are
triggered by `beginCommand` and terminated by `endCommand`.)

Tu circumvent this, Touch Portal X-Plane UDP plugin comes with an addition
X-Plane plugin that will allow for X-Plane long press command to execute properly.

TO install that addition X-Plane plugin, you will need to install the XPPython3 plugin found
[here](https://xppython3.readthedocs.io/en/latest/).

When that plugin is installed and working,
copy the files `PI_tpxp_helper.py` and `states.json` into `<X-Plane>/Resources/Plugins/PythonPlugins` folder.
Make sure you copy the files, do not move the original files.

Reload the XPPython3 plugin scripts so that the above plugin is taken into consideration.

After successful installation and activation of the above plugin, the "Fire Test" command will work.

You will ear Fire Test alarm in the cockpit, and the FIRE button will light RED.



# Afterwords

As simple as it may appears, the Touch Portal X-Plane UDP plugin
opens the door for Touch Portal X-Plane integration.

It is a lot more sophisiticated than existing interfaces
that rely on simulated keystrokes.

You can keep using X-Plane on-screen cockpit elements to control the aircraft.
The state changes will be reported in the Touch Portal user interfaces.

## Proof of Concept

On a personal side, I developed and use this plugin to interface (or port) this
[remarkable user interface design](https://flightsim.to/file/40431/touch-portal-pages-for-flybywire-a32nx)
to X-Plane Toliss A321(neo) aircraft.

Work consisted in the replacement of MS Flight Simulator and plugin specific adjustments
to this (much simpler) plugin (finding commands, datarefs, adjusting events...).

Here is an example of the piedestal. All buttons and data are working.
Please notice the TCAS/ATC panel that has been redone to correspond to the A321neo.

![A321 Main](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/a321-main.png?raw=true)

![A321 Main](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/ipad-main.png?raw=true)

![A321 Piedestal](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/a321-piedestal.png?raw=true)

![A321 Piedestal](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/ipad-piedestal.png?raw=true)

Adjustment to other Toliss Airbus should be straightforward.

DO NO ASK FOR THIS WORK.
I WILL NOT DISTRIBUTE IT WITHOUT PRIOR AUTHORIZATION
OF THE DESIGNER OF THE ABOVE USER INTERFACES.
(Which I haven't got yet.)

Other projects include of course designing cockpits for other aircrafts,
or creating application to inject aircraft defects,
very much like Laminar X-Plane controller application.

Fly safely.
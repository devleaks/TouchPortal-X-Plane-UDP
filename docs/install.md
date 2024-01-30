# Installation and Tests

1. Enable UDP access in X-Plane.
2. In Touch Portal, import the `X-Plane Demo Page.tpz2`
3. In Touch Portal, import the `TouchPortal-X-Plane-UDP_vX.Y_???.tpp` plugin corresponding to your operating system (`???`).
4. In Touch Portal, create a value named pagepath.
5. In Touch Portal, import the flow `Page-Switch.tpe`.
After importing, restart Touch Portal as required.


## Create a value Page Path:

![Page Path value](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/page-path-value.png?raw=true)


## Import a Flow

![Page Switch Event](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/page-switch-event.png?raw=true)


After restarting Touch Portal, have a look at the Touch Portal log page to check if the TouchPortal-Xplane-UDP plugin started.

On your Touch Portal client device, open the X-Plane Demo Page.

Test all features on the demo page, except the Fire Test button.

- Show map, MHz+, and MHz- buttons exercise the simple execution of command.
- The radio frequency display, its color, and the FIRE button exercise behavior changes
when X-Plane dataref values change.
- The Fire Test command exercises the long-press command (press and maintain).
- The "Strobe light" button exercises the "Set Dataref" command.

With the above, you have an example of each tool available through the swiss army knife TouchPortal-Xplane-UDP plugin.

No more. No less.


## Optional installation for "long commands"

On X-Plane, install XPPython3 plugin available [here](https://xppython3.readthedocs.io/en/latest/).

Copy the plugin file `PI_tpxp_helper.py` into `<X-Plane>/Resources/Plugins/PythonPlugins` folder.
Copy the `states.json` file in the same directory. Place a *COPY* of it, do not move the original file.

Reload the XPPython3 plugin scripts so that the above plugin is taken into consideration.

After successful installation and activation of the above plugin, the "Fire Test" command will work.

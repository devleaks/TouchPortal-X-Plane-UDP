# Touch Portal X-Plane UDP Plugin

Touch Portal X-Plane UDP Plugin is a Touch Portal plugin that aims are providing minimal hooks
 - to trigger X-Plane commands,
 - to collect X-Plane dataref values to change appearance of Touch Portal buttons.

Before using the plugin, users must collect information in X-Plane about the datarefs
that will drive button appearance.
This information will be used to create Touch Portal (dynamic) states based on X-Plane datarefs.
The plugin will then ensure that when the dataref value changes, the Touch Portal state changes accordingly.

To interface to X-Plane, the plugin uses X-Plane built-in UDP «API».
This API has shortcomings but is mostly sufficent to create appealing cockpit and dashboards.

For other design operations, Touch Portal creators will use Touch Portal tools to create cockpits and dashboards.


## X-Plane Datarefs and Touch Portal States

To bridge X-Plane Datarefs and Touch Portal States, the plugin uses a simple,
single definition file that establish the link between both.
A link is declared as such

"Touch Portal State Name" = "Expression containing datarefs"

Touch Portal uses the following conventions.

 1. A variable named `variable-name` is accessed by the the syntax {$variable-name$}.

 2. Expressions combining several variables use reverse polish notation (RPN):
    The formula `(2 x variable-name) + 3` is written `{$variable-name$} 2 * 3 +` in RPN.

To avoid bringing new confusing syntax, the Touch Portal X-Plane UDL Plugin uses the same convention.
The Expression containing datarefs will use similar convention.
In an expression, a dataref will be referenced `{$dataref/path/in/simulator$}`.
The expression itself will use RPN.

For exemple, if the dataref `` gives the barometric pressure in inches of mercury,
the following formula convert the pressure in hecto-Pascal (and round it with 0 decimal):
```
"Pressure in hPa" = "{$sim/cockpit/misc/barometer_setting$} 33.8639 * 0 round"
```

Please recall that following the X-Plane UDP protocol, all dataref values returned by the simulator
are `float` numbers.

The above declaration will create a Touch Portal state named `Pressure in hPa` and its value
will reflect the value of the `sim/cockpit/misc/barometer_setting` multiplied by 33.6839 and rounded.

All declarations are in the file `states.json` in a JSON-formatted file.

Declarations all need to be created first before the creator of a page with buttons
can access them in Touch Portal application.

## X-Plane Commands

To execute a command in X-Plane, the Touch Portal creator uses the Execute X-Plane Command action
and supplies the command to execute like `sim/map/show_toggle`.

## X-Plane Dataref Value Change

To change the value of a dataref in the simulator, the creator can use the `Set dataref value` action.
The action will need the dataref that need to be set and the value.

## X-Plane Long Press Command

To execute a long press command in X-Plane, the Touch Portal creator uses the Execute Long Press X-Plane Command action
and supplies the command to execute.

The execution of Long Press command requires a XPPython3 plugin to execute these commands
to circumvent a X-Plane UDP API shortcoming.


Last updated 14-JAN-2024

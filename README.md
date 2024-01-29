[![build](https://github.com/devleaks/TouchPortal-X-Plane-UDP/actions/workflows/build.yml/badge.svg)](https://github.com/devleaks/TouchPortal-X-Plane-UDP/actions/workflows/build.yml)



# Touch Portal X-Plane UDP Plugin

Touch Portal X-Plane UDP Plugin is a Touch Portal plugin that aims at providing minimal hooks
 - to trigger X-Plane commands,
 - to collect X-Plane dataref values to change appearance of Touch Portal buttons.

Before using the plugin, users must collect information in X-Plane about the datarefs
that will drive button appearance.
This information will be used to create Touch Portal (dynamic) states based on X-Plane datarefs.
The plugin will then ensure that when the dataref value changes, the Touch Portal state changes accordingly.

To interface to X-Plane, the plugin uses X-Plane built-in UDP «API».
This API has shortcomings but is mostly sufficent to create appealing cockpit and dashboards.

For other design operations, Touch Portal creators will use Touch Portal tools to create cockpits and dashboards.


## Important Restriction

As currently implemented, the plugin only accepts a single connected client to the Touch Portal server application.

If several users request to lift this restriction, we will consider it
with the warnings and impacts on X-Plane performances (frame rate).


## X-Plane Datarefs and Touch Portal States

To bridge X-Plane Datarefs and Touch Portal States, the plugin uses a simple,
single definition file that establish the link between both.

A link is declared by a small JSON definition like so:

```
    {
        "name": "Pause",
        "formula": "{$sim/time/paused$}",
        "dataref-rounding": 0,
        "type": "int"
    }
```

The above JSON fragment dynamically creates a Touch Portal state named "Pause".

The formula establishes the link between the X-Plane dataref value(s) (in this case `sim/time/paused`,
always a float when fetched through X-Plane UDP API)
and the value of the Touch Portal state (in this case, the state named `Pause`).

The formula uses reverse polish notation (RPN).

Using RPN, the formula `(2 x variable-name) + 3` is written `{$variable-name$} 2 * 3 +`.

To avoid bringing new confusing syntax, the Touch Portal X-Plane UDP Plugin uses the same convention
as the Touch Portal server application.
Touch Portal server application uses RPN in expressions and so does the formula in the plugin.

Touch Portal isolates its internal variables between `{$` and `$}` when writing expressions;
similarly, formula isolates datarefs in framing `{$` and `$}`.
In a formula, a dataref will be referenced `{$dataref/path/in/simulator$}`.

The formula may potentially combine several datarefs into a single state value.

(Note: You cannot use or reference Touch Portal states or values in formula, only dataref values.
So using, for example `${value:tp.plugin.xplaneudp.FCUHEADING}` in a formula is not permitted.)

For exemple, if the dataref `sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot`
gives the barometric pressure in inches of mercury,
the following formula convert the pressure in hecto-Pascal (and round it with 0 decimal):

```
    {
        "name": "Pressure in inHg",
        "formula": "{$sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot$}",
        "dataref-rounding": 2,
        "type": "float",
        "comment": "Just the raw value rounded to 2 decimals"
    },
    {
        "name": "Pressure in hPa",
        "formula": "{$sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot$} 33.8639 * 0 round",
        "dataref-rounding": 3,
        "type": "int"
    }
```

Please recall that following the X-Plane UDP protocol, all dataref values returned by the simulator
are `float` numbers.

The above declaration will create a Touch Portal state named `Pressure in hPa` and its value
will reflect the value of the `sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot` multiplied by 33.6839 and rounded.

If present, the optional `dataref-rounding` is a parameter that rounds the raw dataref value as it is received
from X-Plane before it is substitued in the formula.
It prevents rapidly (and often isignificantly) fluctuating datarefs to provoque too frequent state value changes.
When carefully rounded to a significant value, the dataref update will only provoke a Touch Portal state update when really necessry.

The `type` attribute determine the type of the Touch Portal state value.
In Touch Portal expression string `"1"` is not equal to number value `1`.
Most state values are converted to strings.


## Touch Portal Dynamic State Defintions

[All declarations are in the file](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/states.md)
`states.json` in a JSON-formatted file.
The states in that files are grouped into pages.
When a page is loaded in the Touch Portal client, the states that drive that page
are loaded and monitored. Other states are temporarily not monitored.

If the same state appears in several pages, it must be repeated in each page.
However, internally, it will only be created once.

Declarations all need to be created first before the creator of a page with buttons
can access them in Touch Portal application.



# Touch Portal Actions

## X-Plane Commands

To execute a command in X-Plane, the Touch Portal creator uses the _Execute X-Plane Command_ action
and supplies the command to execute like `sim/map/show_toggle`.

![Execute command](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/execute-command-2.png?raw=true)


## X-Plane Dataref Value Change

To change the value of a dataref in the simulator, the creator can use the _Set dataref value_ action.
The action will need the dataref that need to be set and the value.

Recall that X-Plane UDP protocol will always convert the value to float.

You can only set one value at a time. Not an list or array of values.
To set a value in an array, simply supply its index in the dataref.

![Set dataref](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/set-dataref-2.png?raw=true)


## X-Plane Long Press Command

To execute a long press command in X-Plane, the Touch Portal creator uses the _Execute Long Press X-Plane Command_ action
and supplies the command to execute.

![Execute long press command](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/execute-long-command-2.png?raw=true)

The execution of Long Press command requires a XPPython3 plugin to execute these commands
to circumvent a X-Plane UDP API shortcoming.

The XPPYthon3 plugin is provided with this distribution (`PI_tpxp_helper.py`) and should be placed
in XPPYthon3 plugin script folder.



# Touch Portal Events

Here are a few pieces of Touch Portal code that are executed when values of dynamic stage change.

The process works as follow:

Through the `states.json` file, the plugin creates a Touch Portal dynamic state
and notifies X-Plane that it is interested in getting the values of the datarefs referenced in the formula.

The plugin monitors the dataref values it receives. When a value has really changed (after rounding),
the plugin _computes_ the RPN formula and update the value of the state with the result of the formula.

The plugin change (sends) the value of the dynamic state in Touch Portal server application.

The Touch Portal server application goes through its routine, executing code linked to the state value change events.


## Change of button appearance

![Change button appearance](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/change-appearance-event.png?raw=true)


## Change of button displayed value

![Change of button displayed value](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/baro-value-change.png?raw=true)


## X-Plane Connection Status (change button icon)

![X-Plane Connection Status](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/connection-status-event.png?raw=true)




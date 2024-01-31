[![build](https://github.com/devleaks/TouchPortal-X-Plane-UDP/actions/workflows/build.yml/badge.svg)](https://github.com/devleaks/TouchPortal-X-Plane-UDP/actions/workflows/build.yml)



# Touch Portal X-Plane UDP Plugin

Touch Portal X-Plane UDP Plugin is a Touch Portal plugin that allows Touch Portal creators
to design user interfaces to interact with the X-Plane flight simulator
(cockpit, flight boards, dashboards, applications, etc.).

The plugin adds specific actions to execute commands in the X-Plane simulator.

![Actions](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/actions.png?raw=true)

It also adds convenience states to monitor the connection of the plugin to X-Plane.

![States](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/states.png?raw=true)

Finally,
the plugin also creates dynamic states that have values based on some simulator data values.
Those simulator data values are called datarefs in X-Plane's Universe.

To interface to X-Plane, the Touch Portal X-Plane UDP Plugin uses X-Plane built-in UDP _«API»_.
The X-Plane UDP API has shortcomings but is mostly sufficent to create appealing cockpit and dashboards.


# Actions

![Actions](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/actions.png?raw=true)


## Execute command

To execute a command in X-Plane, the Touch Portal creator uses the _Execute X-Plane Command_ action
and supplies the command to execute like `sim/map/show_toggle`.

![Execute command](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/execute-command-2.png?raw=true)


## Execute long press command

To execute a long press command in X-Plane, the Touch Portal creator uses the _Execute Long Press X-Plane Command_ action
and supplies the command to execute.

![Execute long press command](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/execute-long-command-2.png?raw=true)

A long press command is a command that is executed while the button remain pressed.
It must not be confused with an auto-repeat command.

A long press command is executed once and last for the duration of the pressing on the button.
A command with auto-repeat is a command that will be executed several times,
at given regular interval, for the duration of the pressing on the button.

The execution of Long Press command requires a XPPython3 plugin to execute these commands
to circumvent a X-Plane UDP API shortcoming.

The XPPython3 plugin is provided with this distribution (`PI_tpxp_helper.py`) and should be placed
in XPPython3 plugin script folder.

If the plugin `PI_tpxp_helper.py` is not installed, no long press command will work.


## Set Dataref

To change the value of a dataref in the simulator, the creator can use the _Set dataref value_ action.
The action will need the dataref that need to be set and the value.

Recall that X-Plane UDP protocol will always convert the value to float.

You can only set one value at a time. Not an list or array of values.
To set a value in an array, simply supply its index in the dataref.

![Set dataref](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/set-dataref-2.png?raw=true)


## Leaving Page

The Touch Portal X-Plane UDP Plugin needs to know when a user change page
to load the states that are used on that page.

It also needs to unload the states that are no longer needed.

Touch Portal has a broadcst event sent when a user change page.
The event communicates the new page.
Unfortunately, the event does not tell the page the use is leaving.
(This may change in a future release.)

To get that information, it is nessessary to use the Leave Page command before loading a new page.
The Leave Page command will tell the plugin to unload states that are no longer needed.

![Go to page](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/go-to-page.png?raw=true)

This command may be removed in a future release if Touch Portal change page event tell which page the user is leaving.



# States

In addition to the above commands, the plugin install a few set of states.

![States](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/states.png?raw=true)

These states can be used by user interface creator to communicate the state of the connection
of the Touch Portal plugin to X-Plane.


## Plugin Processes

(Threads of execution.)


### Connection Monitor

The Connection Monitor monitors the connection between the plugin (or Touch Portal)
and the X-Plane simulator.
If the simulator is not running, the Monitor will attempt to connect infinitely
until it can connect to X-Plane.

When connected to X-Plane, it permanently monitor the connetion, attempting to recreate it
if it fails.

The Connection Monitor states is True if the Monitor is running in the plugin.


### Dataref Monitor

The Dataref Monitor is a pair of processes (threads) that

1. Read UDP messages sent by the X-Plane simulator
2. Update the value of the Touch Portal states when a value monitored in the simulator changes.

The Dataref Monitor states is True if the Monitor is running in the plugin.

The Connection Monitor starts and stops the Dataref Monitor if there is or there is no connection to X-Plane.

If the Dataref Monitor runs, it can safely be assumed that the plugin is connected to the simulator
and update the states in Touch Portal when necessary.


# Dynamic States

To create user interfaces, Touch Portal uses _States_, a variable value that
can be set, computed, or simply used in Touch Portal to alter the appearance
of buttons and user interface elements.

In X-Plane, values that change (heading, speed, light is on or off, time of day...)
are all kept in a set of accessible structures called a _Dataref_.
A dataref is accessed by its name, usually a string of characters
organized in domains, very much like a operating system _path_.
Example of dataref name: `sim/map/show_current`.

The Touch Portal X-Plane UDP Plugin has a mechanism to create and maintain
_dynamic_ Touch Portal states based on X-Plane simulator dataref.

Wow.

In other words, there is a mechanism to bring the values of X-Plane in Touch Portal.
When the value changes in X-Plane, the corresponding Touch Portal state value changes.


## Dynamic State Definition

To create a dynamic state, the user must create a piece of JSON-formatted defintion:

```json
    {
        "name": "Pause",
        "formula": "{$sim/time/paused$}",
        "dataref-rounding": 0,
        "type": "int"
    }
```

The above JSON fragment dynamically creates a Touch Portal dynamic state named "Pause".

The `formula` establishes the link between the X-Plane dataref value(s) (in this case `sim/time/paused`)
and the value of the Touch Portal state (in this case, the state named `Pause`).

The `type` attribute determine the type of the Touch Portal state value.
In Touch Portal expression string `"1"` is not equal to number value `1`.
In the plugin, most state values are converted to strings.

The optional `dataref-rounding` is a rounding that is applied to a dataref value
before it is used.
The reason this is provided is that dataref values often fluctuates with little significance.
So, to limit the frequency of the updates of the related dynamic state,
a rouding is applied first to ensure significant change has occured.


### Formula

The `formula` establishes the link between the X-Plane dataref value(s)
and the value of the Touch Portal state.

To avoid bringing new confusing syntax, the Touch Portal X-Plane UDP Plugin uses the same convention
as the Touch Portal server application.
Touch Portal server application uses Reverse Polish Notation (RPN) in expressions and so does the formula in the plugin.

Using RPN, the formula `(2 x variable-name) + 3` is written `variable-name 2 * 3 +`.

Touch Portal isolates its internal variables between `{$` and `$}` when writing expressions;
similarly, formula isolates datarefs in framing `{$` and `$}`.
In a formula, a dataref will be referenced `{$dataref/path/in/simulator$}`.

The formula may potentially combine several datarefs into a single state value.

(Note: You cannot use or reference Touch Portal states or values in formula, only dataref values.
So using, for example `${value:tp.plugin.xplaneudp.FCUHEADING}` in a formula is not permitted.)

Finally, please recall that following the X-Plane UDP protocol,
all dataref values returned by the simulator are `float` numbers.


### Example

For exemple, the dataref `sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot`
gives the barometric pressure in inches of mercury.
The following formula convert the pressure in hecto-Pascal (and round it with 0 decimal):

```json
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


The above declaration will create a Touch Portal dynamic state named `Pressure in hPa` and its value
will reflect the value of the `sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot` multiplied by 33.6839 and rounded.

The `dataref-rounding` is a parameter that rounds the raw dataref value as it is received
from X-Plane before it is substitued in the formula.

It prevents rapidly (and often insignificantly) fluctuating datarefs to provoque too frequent state value changes.
When carefully rounded to a significant value, the dataref update will only provoke a Touch Portal state update when really necessry.


## Dynamic State File

All declarations are in the file `states.json`, a JSON-formatted file.
The format of the file is detailed
[here](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/states.md).

States in that files are grouped into pages.
When a page is loaded in the Touch Portal client, the states that drive that page
are loaded and monitored. Other states are temporarily not monitored.

If the same state appears in several pages, it must be repeated in each page.
However, internally, it will only be created once.

Declarations all need to be created first before the creator of a page with buttons
can access them in Touch Portal application.


# Touch Portal Events

Here are a few pieces of Touch Portal plugin code that are executed when values of dynamic stage change.

The process works as follow:

Through the `states.json` file, the plugin creates a Touch Portal dynamic state
and notifies X-Plane that it is interested in getting the values of the datarefs referenced in the formula.

The plugin Dataref Monitor monitors the dataref values it receives.
When a value has really changed (after rounding),
the plugin _computes_ the RPN formula and update the value of the state with the result of the formula.

The plugin change (sends) the value of the dynamic state in Touch Portal server application.

The Touch Portal server application goes through its routine, executing code linked to the state value change events.


## Change of button appearance

![Change button appearance](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/change-appearance-event.png?raw=true)


## Change of button displayed value

![Change of button displayed value](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/baro-value-change.png?raw=true)


## X-Plane Connection Status (change button icon)

![X-Plane Connection Status](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/connection-status-event.png?raw=true)


## Important: Change of Pages

When using standard Touch Portal action "Go to page", it is necessary to prepend this instruction
with another instruction.
Touch Portal notifies the plugin of the page it is entering, but not the page it is leaving.
The above instruction simply add that information.

![X-Plane Connection Status](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/go-to-page.png?raw=true)

Please note that to work correctly,
the instruction relies on a global Touch Portal Event (called _Switch Page_).
The global Touch Portal Event Switch Page automagically populates the Touch Portal value _Page Path_
when a user changes page.
The Page Path value is used by the Leave Page action to report which page a user is leaving.

# Installation

Details are [here](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/install.md).

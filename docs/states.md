# Notes on Dynamic Plugin Touch Portal States

All definitions of states are grouped in a `states.json` file.

The file is located in the Touch Portal plugin folder.

The structure of the file is:

```json
{
    "version": 1,
    "pages": [
        {
            "name": "page name as it is in Touch Portal",
            "states": [
                {
                    "name": "state name",
                    "formula": "state formula",
                    "dataref-rouding": 2,
                    "type": "int|float|bool"
                },
                { other dynamic states... }
            ]
        },
        { other pages... }
    ],
    "long-press-commands": [
        "long/press/command"
    ]
}
```

## Version

The version attribute is mandatory is determine the format of the file.

## Pages

All pages are grouped in a `pages` attributes.
It is an array/list of page structures.

Each page has the following attributes:

### Page Name

The page name must be the full name, including folder(s) path and `.tml` extension.

```
    "name": "/X-Plane Demo.tml"
```

or

```
    "name": "/Airbus A321/A32NX_MAIN.tml"
```

### Dynamic State Definitions

Dynamic states definition are listed in the `states` attribute.

Each dynamic state definition has the following attribute:

#### Name

The name of the dynamic state as it appears in Touch Portal.

IMPORTANT: The Touch Portal X-Plane UDP plugin creates an internal
name for this state based on its displayed name.
If you change the displayed name, the internal name will also change.

#### Formula

See the
[README](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/README.md)
file.

#### Type

The state `type` forces the value forwarded to Touch Portal to a given type.

Valid types are:

 - `int`: No decimal point, no decimal part, like 1013.
 - `float`: With decimal part, 3.1415926.
 - `bool`: exclusively the word TRUE or FALSE (a string, all capital letters).
 - `boolint`: exclusively the value "0" or "1" (integer value, no decimal)

Additional attributes may be added to the state or page definitions,
like "comments" but are ignored.


# Cheats, Internal Features


## Dynamic State Value Formatting

In a later release, `type` will aim at providing formatting information as well.

Currently

`int04`

will format as

`{:04d}`

Same for floats (`float5.3` -> `{:5.3f}`).

Format expressed after `int` or `float` keywords must be a valid python number format.


## Reloading the states.json file

During development process, when new dynamic states are created,
it is convenient to reload the states.json file.

To do so, add a Touch Portal action "Execute X-Plane command", and as
an action to execute, add the secret keywork RELOAD_STATES_FILE string (all uppercase letters).

![Reload states file](https://github.com/devleaks/TouchPortal-X-Plane-UDP/blob/main/docs/reload-states-file.png?raw=true)

When triggered, this action will reload the state file, deleting states
that no longer exists in the file and adding new states if any.

If the page has errors, is misformatted, etc. it is not releaded.

This is solely used during development process, when the page developer
creates new dynamic states for X-Plane interaction.

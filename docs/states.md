# Notes on Dynamic Plugin Touch Portal States

The structure of the file is:

```yaml
  states.json
    version
    home-page: page_name
    sub-folder: touchportal_page_folder_path
    pages:
      -
        name: page_name
        states:
          -
            name: state_name
            formula: state formula
            dataref-rouding: rounding applied to all datarefs in formula before comparison
            type: {int|float|bool} type of state value sent to Touch Portal (bool={TRUE|FALSE} as text strings)
          -
            ...
    "long-press-commands": [
        "long/press/command"
    ]

```

Note that the value of a dataref as received from X-Plane is always a float.

The page name will be search in Touch Portal page folder named after `sub-folder` attribute.
This parameter is optional if all pages are in the root folder.

The state type forces the value forwarded to Touch Portal to a given type.
Valid types are:

 - `int`: No decimal point, no decimal part
 - `float`: With decimal part
 - `bool`: exclusively the word TRUE or FALSE (a string, all capital letters).
 - `boolint`: exclusively the value 0 or 1 (integer value, no decimal)

Additional attributes may be added, like "comments" but are ignored.

# Cheats

## Type formatting

Type will aim at providing format information as well.

Currently

`int04`

will format as

`{:04d}`

Same for floats (float5.3 -> {:5.3f}).
Format after `int` or `float` keywords must be a valid python number format.

## Reloading the states.json file

During development process, when new dynamic states are created, it is convenient
to reload the states.json file.

To do so, add a Touch Portal action "Execute X-Plane command", and as
an action to execute, add the secret keywork RELOAD_STATES_FILE string.

When triggered, this action will reload the state file, deleting states
that no longer exists in the file and adding new states if any.

This is solely used during development process, when the page developer
creates new dynamic states for X-Plane interaction.


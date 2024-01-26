# Notes on Dynamic Plugin Touch Portal States

The structure of the file is:

```yaml
  states.json
    version
    home-page: page_name
    sub-folder: directory_path
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
This parameter is optional if all pages are in the root folder for example.

The state type forces the value forwarded to Touch Portal to a given type.
The value of a state sent to Touch Portal is always a string.
Valid types are:

 - `int`: No decimal point, no decimal part
 - `float`: With decimal part
 - `bool`: exclusively the word TRUE or FALSE (capital letter).
 - `boolint`: exclusively the value 0 or 1

## Cheat

type will aim at providing format information as well.

Currently

`int04`

will format as

`{:04d}`

Same for floats (float5.3 -> {:5.3f}).
Format after `int` or `float` keywords must be a valid python number format.

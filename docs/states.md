# Notes on Dynamic Plugin Touch Portal States

The structure of the file is:

```yaml
  states.json
     version
     pages:
       -
         name: page_name
         states:
           -
             name: state_name
             formula: state formula
             dataref-rouding: rounding applied to all datarefs in formula before comparison
             type: {int|float|bool} type of state value sent to Touch Portal (bool={TRUE|FALSE})
           -
```
Note that the value of a dataref is always a float.


The state type forces the value forwarded to Touch Portal to a give type.
Note that the value of a state is always a string

 - int: No decimal point, no decimal part
 - float: With decimal part
 - bool: exclusively the word TRUE or FALSE (capital letter).

 
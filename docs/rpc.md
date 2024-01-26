# Notes on Reverse Polish Notation

All values on the RPN stack are float value or functions.
Integer values are converted to float.
Non float values are assumed to be functions.

The following functions are available in RPN:

  - Mathematical operations: +, -, x, /.
  - Modulo (% operator in Python)
  - Floor
  - Ceil
  - Round (uses precedding integer as rounding factor: `0.55 1 round` -> `0.6`)
  - Abs (absolute value)
  - Eq (is equal: Check equality of last two values, pushed 0.0 or 1.0 on stack)
  - Not (pushed 1.0 if pop() is 0.0 else pushes 0.0)

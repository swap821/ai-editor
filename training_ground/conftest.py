"""Make the sandbox importable the way a test sitting next to a module expects.

`training_ground/` carries an `__init__.py`, so it is a package, and the agent's
verify command runs from the repo root (`Executor._scope_cwd`). Under pytest's
default `prepend` import mode a test inside a package gets the package's PARENT
on `sys.path` -- the repo root -- and never the package directory itself. So

    from calculator import Calculator      # test_calculator.py, calculator.py side by side

raised `ModuleNotFoundError: No module named 'calculator'`, while

    from training_ground.calculator import Calculator

worked. Both are reasonable things to write; only one of them ran.

That decided golden missions. `multi-module` is the only mission whose prompt
names the package path ("imports validate_email from training_ground.validator")
and it passed 3/3 on gemini-3.7-flash. `tdd-workflow` and `iterative-refinement`
give no import guidance, the model wrote the bare import a developer would write,
and they failed 3/3 and 2/3 -- scored as the model's code failing its own tests
when the code was fine and the sandbox could not import it.

Inserting this directory on `sys.path` makes both spellings work. It changes no
mission, no verifier, and no pass criterion: the tests still have to pass. It
only stops the sandbox from rejecting correct code for where it sits.
"""

import sys
from pathlib import Path

_SANDBOX_DIR = str(Path(__file__).resolve().parent)
if _SANDBOX_DIR not in sys.path:
    sys.path.insert(0, _SANDBOX_DIR)

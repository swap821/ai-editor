"""Testable module with NO corresponding test -> a 'missing_test' finding.

Also imports a sibling module, freezing one intra-package import-map edge (T0).
"""
import pkg.tidy


def lonely():
    return pkg.tidy.add(1, 2)

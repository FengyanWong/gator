"""Spectre deck text around a structure-only export: the header (simulator language, models, options) and the five-
transistor OTA's DC/AC analyses. Moved here from virtuoso_bridge.py (which still exports both) by the optimizer
clean-up of 2026-10-09 (plan-refactoring E6)."""
import re

from .conditions import finite_number


def build_deck_header(structure, model_file, section='tt', *, temperature_c=27.0):
    if not model_file.startswith('/') or any(c in model_file for c in '\n\r"'):
        raise ValueError('Model file must be an absolute Spectre-host path')
    if not re.fullmatch(r'[A-Za-z_]\w*', section):
        raise ValueError('Invalid model section')
    if re.search(r'^\s*(include|ahdl_include|simulator|global)\b', structure, re.M):
        raise ValueError('Expected structure-only export')
    if not finite_number(temperature_c) or temperature_c <= -273.15:
        raise ValueError('Invalid simulation temperature')
    return ('simulator lang=spectre\nglobal 0\n'
            + f'include "{model_file}" section={section}\n' + structure + '\n'
            + f'simulatorOptions options reltol=1e-5 vabstol=1e-8 iabstol=1e-13 temp={temperature_c:.12g} tnom=27\n')


def build_deck(structure, model_file, section='tt', *, temperature_c=27.0):
    return (build_deck_header(structure, model_file, section, temperature_c=temperature_c)
            + 'dcOp dc\ndcOpInfo info what=oppoint where=rawfile\n'
            + 'ac ac start=10 stop=1G dec=60\n'
            + 'save VOUT VINP VINN VDD VBIAS XU1.NTAIL XU1.NLOAD VDD:p\n'
            + 'saveOptions options save=allpub\n')

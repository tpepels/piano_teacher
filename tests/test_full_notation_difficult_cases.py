"""Full independent symbol acceptance for original dense-source audit cases.

Unlike the focused staff-rail probe this executes ALL current graphical,
semantic, rest, connector, beam, tuplet, ledger and unexpected-symbol proofs.
Do not narrow the expected symbol set or turn unverified into verified.
"""
import json
from pathlib import Path
import shutil

import pytest

from scripts.check_native_verovio_overlay import AuditCase, run


@pytest.mark.parametrize("name,source,first,last,hand", (
    ("hanon-37", "Le_Pianiste_virtuose_-_Première_partie_(1-20)_-_C_L_Hanon.midi", 37, 40, "left"),
    ("chopin-13", "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 13, 16, "right"),
))
def test_every_native_symbol_on_difficult_real_source(
        name, source, first, last, hand, tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    assert godot, "Actual Godot native renderer is mandatory"
    case = AuditCase("full-native-"+name,source,first,last,hand)
    folder = tmp_path/name
    outcome = run(folder,godot,case,all_symbols=True,strict=False)
    (folder/"full-source-result.json").write_text(
        json.dumps(outcome,indent=2,default=str))
    assert not outcome["errors"], {
        "case":name,"source":source,
        "error_count":len(outcome["errors"]),
        "first_errors":outcome["errors"][:25],
        "report":str(folder/"full-source-result.json")
    }

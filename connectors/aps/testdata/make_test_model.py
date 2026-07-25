"""Generate the APS validation-gate test model (aps_test_model.dxf).

Follows the validation-first pattern from docs/ABSORBED_PATTERNS.md section 10:
every meaningful dimension is a named parameter, geometry lands on named
layers, and the file regenerates from source instead of hand edits. The model
is synthetic — a rectangular parcel boundary with a building pad and two
easement lines — so it carries zero client or employer data and is safe to
upload to a sandbox APS bucket.

Usage: python make_test_model.py  (writes aps_test_model.dxf next to itself)
"""

from pathlib import Path

import ezdxf

PARCEL_W = 300.0   # ft
PARCEL_H = 200.0   # ft
PAD_W = 80.0       # ft
PAD_H = 50.0       # ft
PAD_OFFSET = (60.0, 60.0)
EASEMENT_SETBACK = 25.0  # ft from parcel edge

LAYERS = {
    "V-PARCEL": 1,
    "V-BLDG-PAD": 3,
    "V-EASEMENT": 5,
    "V-ANNO": 7,
}


def gen_dxf() -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 2  # feet
    msp = doc.modelspace()
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)

    parcel = [(0, 0), (PARCEL_W, 0), (PARCEL_W, PARCEL_H), (0, PARCEL_H)]
    msp.add_lwpolyline(parcel, close=True, dxfattribs={"layer": "V-PARCEL"})

    px, py = PAD_OFFSET
    pad = [(px, py), (px + PAD_W, py), (px + PAD_W, py + PAD_H), (px, py + PAD_H)]
    msp.add_lwpolyline(pad, close=True, dxfattribs={"layer": "V-BLDG-PAD"})

    msp.add_line((EASEMENT_SETBACK, 0), (EASEMENT_SETBACK, PARCEL_H),
                 dxfattribs={"layer": "V-EASEMENT"})
    msp.add_line((0, PARCEL_H - EASEMENT_SETBACK), (PARCEL_W, PARCEL_H - EASEMENT_SETBACK),
                 dxfattribs={"layer": "V-EASEMENT"})

    msp.add_text("APS VALIDATION GATE TEST MODEL — SYNTHETIC, NO PROJECT DATA",
                 height=8, dxfattribs={"layer": "V-ANNO"}).set_placement((10, PARCEL_H + 15))
    return doc


def validate(doc: ezdxf.document.Drawing) -> dict:
    msp = doc.modelspace()
    by_layer: dict[str, int] = {}
    closed_polylines = 0
    for e in msp:
        by_layer[e.dxf.layer] = by_layer.get(e.dxf.layer, 0) + 1
        if e.dxftype() == "LWPOLYLINE" and e.closed:
            closed_polylines += 1
    checks = {
        "entities_by_layer": by_layer,
        "closed_polylines": closed_polylines,
        "expected_closed_polylines": 2,
        "units_feet": doc.header["$INSUNITS"] == 2,
    }
    checks["pass"] = (
        closed_polylines == 2
        and by_layer.get("V-PARCEL") == 1
        and by_layer.get("V-BLDG-PAD") == 1
        and by_layer.get("V-EASEMENT") == 2
        and checks["units_feet"]
    )
    return checks


if __name__ == "__main__":
    out = Path(__file__).with_name("aps_test_model.dxf")
    doc = gen_dxf()
    doc.saveas(out)
    result = validate(ezdxf.readfile(out))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(result)
    raise SystemExit(0 if result["pass"] else 1)

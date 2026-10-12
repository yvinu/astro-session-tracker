"""The Optical Train: a File's equipment, as stored values and as a label.

Telescope name, camera and focal length are stored on each File as
values. The label joins whichever of them are present and is for
display and for Rig patterns; nothing reads values back out of it.

Two labels exist for one File. The measured label carries the focal
length exactly as the header gave it, which for a plate-solved frame
differs a little every night. The nominal label is for reading: a File
with a Rig shows the Rig's name and nominal focal length, so one set-up
is one entry in a filter however its headers spelled it.

Standard library only: the Mac command-line tool imports this.
"""

SEPARATOR = " | "


def focal_length_value(raw):
    """A header's focal length as a positive number of millimetres, or None."""
    try:
        value = float(str(raw).strip().lower().removesuffix("mm"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def text_value(raw):
    """A header's text value, or None when it is absent or blank."""
    text = "" if raw is None else str(raw).strip()
    return text or None


def format_focal(focal_length):
    """A focal length for a label: '370mm', '372.53mm'."""
    return f"{focal_length:g}mm"


def label(telescope, instrument, focal_length):
    """Join whichever of telescope, camera and focal length are present; 'Unknown' when none is.

    One missing value does not make the whole label unknown: a set-up
    with no telescope name is still identifiable.
    """
    parts = [str(part).strip() for part in (telescope, instrument) if part not in (None, "")]
    if focal_length not in (None, ""):
        parts.append(f"{focal_length}mm")
    return SEPARATOR.join(parts) if parts else "Unknown"


def nominal_label(measured_label, telescope, instrument, focal_length, rig=None):
    """The label to show when focal lengths are simplified.

    With a Rig: its name, and its nominal focal length if it has one.
    Without: the measured label with the focal length rounded to a whole
    millimetre, which is the best that can be said of a File no Rig claims.
    """
    if rig:
        nominal = rig.get("focal_nominal")
        return rig["name"] if nominal is None else f"{rig['name']}{SEPARATOR}{format_focal(float(nominal))}"
    if focal_length is None:
        return measured_label
    return label(telescope, None if instrument in (None, "", "Unknown") else instrument, round(focal_length))

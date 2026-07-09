import numpy as np
import pytest
from astropy.io import fits


def _write_fits(path, header_cards):
    data = np.zeros((2, 2), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    for key, value in header_cards.items():
        hdu.header[key] = value
    hdu.writeto(path, overwrite=True)


@pytest.fixture
def make_fits(tmp_path):
    """Factory fixture: make_fits('name.fits', {'IMAGETYP': 'Light Frame', ...}) -> str path."""
    def _make(filename, header_cards=None):
        path = tmp_path / filename
        _write_fits(str(path), header_cards or {})
        return str(path)
    return _make

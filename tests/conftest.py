import numpy as np
import pytest
from astropy.io import fits


def _write_fits(path, header_cards, shape):
    data = np.zeros(shape, dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    for key, value in header_cards.items():
        hdu.header[key] = value
    hdu.writeto(path, overwrite=True)


@pytest.fixture
def make_fits(tmp_path):
    """Factory fixture: make_fits('name.fits', {'IMAGETYP': 'Light Frame', ...}) -> str path.

    `shape` is the numpy array shape (rows, cols) written as image data --
    astropy derives NAXIS1 (=cols, width) / NAXIS2 (=rows, height) from it,
    overriding any NAXIS1/NAXIS2 passed in header_cards, so pass shape
    directly when a test cares about the resulting resolution.
    """
    def _make(filename, header_cards=None, shape=(2, 2)):
        path = tmp_path / filename
        _write_fits(str(path), header_cards or {}, shape)
        return str(path)
    return _make

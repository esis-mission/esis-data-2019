# esis-data-2019
The FITS files captured during the ESIS flight on September 30th, 2019.

## AIA images

The `aia-v1.0` release holds `esis-2019-aia-lev1.tar`, the images from the 193 and 304 Å channels of the Atmospheric Imaging Assembly (AIA) on the Solar Dynamics Observatory in the 12 s time slots from 18:06 to 18:12 UTC.
They span the Level-1 observations of ESIS, from 18:06:11.6 to 18:11:11.6 UTC.
They are the Level 1 files the JSOC serves, unchanged, so the `esis` package can use them without depending on the JSOC.
The archive's `manifest.csv` lists the JSOC record, times, exposure, quality flag, and SHA-256 checksum of each image.

`tools/build_aia.py` builds the archive from the JSOC, using `astropy` and `drms`:

    python tools/build_aia.py <directory>

The images are courtesy of NASA/SDO and the AIA science team.
Please cite [Lemen et al. (2012)](https://doi.org/10.1007/s11207-011-9776-8) when you use them.

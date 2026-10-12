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

## AIA and XRT images of event E

The `event-e-v1.0` release holds `esis-2019-event-e.tar`, the images which the article on event E, the jet at about (48″, −88″), inverts for its differential emission measure from 18:00 to 18:20 UTC.

- `xrt/`: every Al_poly image of the X-Ray Telescope (XRT) on Hinode which began in that time, 64 of them. They are the Level 1 files of the Solar Data Analysis Center, unchanged.
- `aia/`: every image from the 94, 131, 171, 193, 211, 304, and 335 Å channels of AIA in the 12 s time slots from 17:59:36 to 18:20:36 UTC, 105 per channel. That includes the image in each channel closest to the middle of every XRT exposure.
  - The full-disk images of those 21 minutes would be about 6.6 GB. So each image is registered with `sdo.aia.prep`, which rotates it to solar north up and scales it to 0.6″ per pixel.
  - A cutout 400 pixels (240″) on a side around event E is then kept, as 32-bit floating point.
  - Registration puts every image on one grid, so the cutouts share one grid too.
  - The header of each cutout is that of the registered image, with the reference pixel moved to the cutout. Its history records the versions of `aiapy`, `sunpy`, and `solar-dynamics-observatory` which registered it.

The `manifest.csv` of each directory lists where each file came from, its time, filter or channel, exposure, and SHA-256 checksum. For AIA it also lists the checksum of the Level 1 image each cutout was cut from.

`tools/build_event_e.py` builds the archive from the JSOC and the Solar Data Analysis Center, using `drms`, `sdo`, and `hinode`:

    python tools/build_event_e.py <directory>

The XRT images are courtesy of the Hinode team. Hinode is a Japanese mission developed and launched by ISAS/JAXA, with NAOJ as a domestic partner and NASA and STFC (UK) as international partners. It is operated by these agencies in cooperation with ESA and NSC (Norway).
Please cite [Golub et al. (2007)](https://doi.org/10.1007/s11207-007-0182-1) for XRT and [Lemen et al. (2012)](https://doi.org/10.1007/s11207-011-9776-8) for AIA when you use them.

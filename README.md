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

## Images of event E

The `event-e-v1.1` release holds `esis-2019-event-e.tar`, the images which the article on event E, the jet at about (48″, −88″), uses.
It inverts the differential emission measure of event E from 18:00 to 18:20 UTC from:

- `xrt/`: every Al_poly image of the X-Ray Telescope (XRT) on Hinode which began in that time, 64 of them. They are the Level 1 files of the Solar Data Analysis Center, unchanged.
- `aia/`: every image from the 94, 131, 171, 193, 211, 304, and 335 Å channels of AIA in the 12 s time slots from 17:59:36 to 18:20:36 UTC, 105 per channel. That includes the image in each channel closest to the middle of every XRT exposure.
  - The full-disk images of those 21 minutes would be about 6.6 GB. So each image is registered with `sdo.aia.prep`, which rotates it to solar north up and scales it to 0.6″ per pixel.
  - A cutout 400 pixels (240″) on a side around event E is then kept, as 32-bit floating point.
  - Registration puts every image on one grid, so the cutouts share one grid too.
  - The header of each cutout is that of the registered image, with the reference pixel moved to the cutout. Its history records the versions of `aiapy`, `sunpy`, and `solar-dynamics-observatory` which registered it.

Beside them are:

- `hmi/`: every line-of-sight magnetogram of the Helioseismic and Magnetic Imager (HMI) on the Solar Dynamics Observatory in the 45 s time slots of the same 21 minutes, 28 of them.
- `hmi_history/`: every 720 s line-of-sight magnetogram of HMI from 18:00 TAI on 2019 September 29 to 20:00 TAI on September 30, a day before event E to two hours after, 131 of them, for the history of the flux beneath it.
  - The JSOC stores the magnetograms without their keywords, so the header of each is made from the keywords the JSOC keeps for it.
  - Each is then registered with `aiapy.calibrate.register`, like the AIA images, and a cutout 400 pixels (240″) on a side is kept, as 32-bit floating point, in gauss.
  - The 45 s cutouts are on the grid of the AIA cutouts, pixel for pixel.
  - The 720 s cutouts follow event E across the disk as the Sun rotates. Each is centered where the surface at the center of the AIA cutouts at 18:10 UTC is at its own time, about 220″ further east a day before.
  - The QUALITY of a few magnetograms has the bit `0x00010000` (`QUAL_LOWINTERPNUM`) set, by the daily calibrations of HMI at 06:00 and 18:00 UTC. No other bit is set in any of them.
- `iris/`: the slit-jaw images at 1400 Å of observation 3604109624 of the Interface Region Imaging Spectrograph (IRIS), from 17:19 to 18:28 UTC, which spans the flight. It is the Level 2 file of the Lockheed Martin Solar and Astrophysics Laboratory, unchanged. Its field, 172″ by 182″ around disk center, holds most of event E but cuts through its base at its bottom edge.

The `manifest.csv` of each directory lists where each file came from, its time, filter or channel, exposure, and SHA-256 checksum. For AIA and HMI it also lists the checksum of the full-disk image each cutout was cut from.

The `event-e-v1.0` release holds only `xrt/` and `aia/`, byte for byte the same as in `event-e-v1.1`.

`tools/build_event_e.py` builds the archive from the JSOC, the Solar Data Analysis Center, and the Lockheed Martin Solar and Astrophysics Laboratory, using `drms`, `aiapy`, `sunpy`, `sdo`, and `hinode`:

    python tools/build_event_e.py <directory>

The XRT images are courtesy of the Hinode team. Hinode is a Japanese mission developed and launched by ISAS/JAXA, with NAOJ as a domestic partner and NASA and STFC (UK) as international partners. It is operated by these agencies in cooperation with ESA and NSC (Norway).
The AIA images and the HMI magnetograms are courtesy of NASA/SDO and the AIA and HMI science teams.
IRIS is a NASA small explorer mission developed and operated by LMSAL with mission operations executed at NASA Ames Research Center and major contributions to downlink communications funded by ESA and the Norwegian Space Centre.
Please cite [Golub et al. (2007)](https://doi.org/10.1007/s11207-007-0182-1) for XRT, [Lemen et al. (2012)](https://doi.org/10.1007/s11207-011-9776-8) for AIA, [Scherrer et al. (2012)](https://doi.org/10.1007/s11207-011-9834-2) and [Schou et al. (2012)](https://doi.org/10.1007/s11207-011-9842-2) for HMI, and [De Pontieu et al. (2014)](https://doi.org/10.1007/s11207-014-0485-y) for IRIS when you use them.

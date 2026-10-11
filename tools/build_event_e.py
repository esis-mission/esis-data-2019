"""
Build the archive of the AIA and XRT images of event E.

Event E is the jet at about (48, -88) arcseconds which ESIS observed during
its flight on 2019 September 30. The archive holds the images which the
article on event E inverts for its differential emission measure (DEM)
from 18:00 to 18:20 UTC, from when the jet begins to brighten in X-rays to
after it has faded:

- every Al_poly image of the X-Ray Telescope (XRT) on Hinode which began
  in that time, the Level 1 files of the Solar Data Analysis Center,
  unchanged;
- every image from seven EUV channels of the Atmospheric Imaging Assembly
  (AIA) on the Solar Dynamics Observatory in the JSOC's 12 second time slots
  from 17:59:36 to 18:20:36 UTC, which includes the image in each channel
  closest to the middle of every XRT exposure.
  The six channels of the DEM are there, and 304 Angstroms, which the
  article uses to co-align ESIS.

The full-disk AIA images of those 21 minutes are about 6.6 GB, so the
archive keeps a cutout of each one, 400 pixels (240 arcseconds) on a side
around event E, after the image is registered with
:func:`sdo.aia.prep`, which rotates it to solar north up and scales it to
0.6 arcseconds per pixel.
Registration puts every image on the same grid, so the cutouts are taken at
the same coordinates in every image and share a grid too.
The data of each cutout is stored as 32-bit floating point, and its header
is the registered image's, with the reference pixel moved to the cutout.

Manifests record where each file came from, its time, channel or filter,
exposure, and the SHA-256 checksums of the file and, for AIA, of the Level
1 image it was cut from.

Run it as ``python tools/build_event_e.py <directory>``. It downloads the
images into ``<directory>``, prepares the cutouts there, and writes
``<directory>/esis-2019-event-e.tar``, whose contents and bytes depend only
on the images and on the versions of :mod:`aiapy` and :mod:`sunpy` which
registered them, which the header of each cutout records.
"""

import concurrent.futures
import csv
import importlib.metadata
import pathlib
import shutil
import sys
import tarfile
import astropy.io.fits
import astropy.time
import astropy.units as u
import astropy.wcs
import numpy as np
import named_arrays as na
import hinode
import sdo
from build_aia import download, header, normalize, query, sha256
import build_aia

time_start_aia = "2019-09-30T17:59:36Z"
"""The first time slot of the AIA images."""

duration_aia = "21m"
"""How long after :data:`time_start_aia` the AIA images extend, in JSOC notation."""

channels = (94, 131, 171, 193, 211, 304, 335)
"""The AIA channels in the archive, in Angstroms."""

time_start_xrt = "2019-09-30T18:00:00"
"""The earliest start of the XRT images."""

time_stop_xrt = "2019-09-30T18:20:00"
"""The latest start of the XRT images."""

filter_xrt = "Al_poly"
"""The filter of the XRT images."""

center = (51, -67) * u.arcsec
"""
The center of the cutouts, in helioprojective coordinates.

That is the center of the region the article inverts, the 128 by 128 XRT
pixels around event E, whose position changes by less than two arcseconds
over the 20 minutes.
"""

num_pixel = 400
"""The number of pixels on each side of the cutouts."""

name_archive = "esis-2019-event-e.tar"
"""The name of the archive."""

name_manifest = "manifest.csv"
"""The name of the manifest in each directory of the archive."""

keys_aia = ("T_OBS", "DATE-OBS", "WAVELNTH", "EXPTIME", "QUALITY")
"""The keywords copied from the header of each AIA image into its manifest."""

keys_xrt = ("DATE_OBS", "EC_FW1_", "EC_FW2_", "EXPTIME")
"""The keywords copied from the header of each XRT image into its manifest."""

num_workers = 6
"""How many images to register at once."""

num_downloads = 3
"""
How many images to download from the JSOC at once, which refuses many
requests at once but serves a few faster than one.
"""


def name_cutout(name_lev1: str) -> str:
    """The name of the cutout of the AIA image whose JSOC name is given."""
    return name_lev1.replace("image_lev1.fits", "image_lev15_event_e.fits")


def cutout(path_lev1: pathlib.Path, path: pathlib.Path) -> None:
    """
    Register one AIA image and save the cutout around event E.

    The registered full-disk image is 134 MB, so it is deleted once the
    cutout is saved.
    """
    files = sdo.aia.prep(
        files=na.ScalarArray(np.array([str(path_lev1)], dtype=object), axes="file"),
        register=True,
        cache=None,
    )
    path_15 = pathlib.Path(files.ndarray[0])

    with astropy.io.fits.open(path_15, memmap=False) as hdul:
        hdu = hdul[0]
        h = hdu.header.copy()
        data = hdu.data
    wcs = astropy.wcs.WCS(h)

    corner = center - num_pixel / 2 * 0.6 * u.arcsec
    x, y = wcs.world_to_pixel_values(
        corner[0].to_value(u.deg), corner[1].to_value(u.deg)
    )
    x0, y0 = int(np.rint(x)), int(np.rint(y))
    data = data[y0 : y0 + num_pixel, x0 : x0 + num_pixel].astype(np.float32)
    if data.shape != (num_pixel, num_pixel):
        raise ValueError(f"{path_lev1.name}: the cutout leaves the image")

    h["CRPIX1"] = h["CRPIX1"] - x0
    h["CRPIX2"] = h["CRPIX2"] - y0
    # Only meaningful for integer data, and astropy warns about it on floats.
    h.remove("BLANK", ignore_missing=True)
    # astropy.wcs warns that it computes this from DATE-OBS when it is missing.
    h["MJD-OBS"] = astropy.time.Time(h["DATE-OBS"]).mjd
    for package in ("aiapy", "sunpy", "solar-dynamics-observatory"):
        h.add_history(
            f"Registered with {package} {importlib.metadata.version(package)}"
        )
    h.add_history(
        f"Cut out pixels [{y0}:{y0 + num_pixel}, {x0}:{x0 + num_pixel}] of the registered image"
    )

    path_partial = path.with_name(path.name + ".part")
    astropy.io.fits.PrimaryHDU(data=data, header=h).writeto(
        path_partial, overwrite=True
    )
    path_partial.replace(path)
    path_15.unlink()


def build_aia_cutouts(directory: pathlib.Path) -> list[pathlib.Path]:
    """Download the AIA images, register them, and save their cutouts."""
    directory_lev1 = directory / "aia_lev1"
    directory_aia = directory / "aia"
    directory_lev1.mkdir(parents=True, exist_ok=True)
    directory_aia.mkdir(parents=True, exist_ok=True)

    rows = query(time_start_aia, duration_aia, channels)
    rows.sort(key=lambda r: (int(r["WAVELNTH"]), r["T_REC"]))
    print(f"{len(rows)} AIA images", flush=True)

    def fetch(row: dict[str, str]) -> pathlib.Path:
        path_lev1 = directory_lev1 / build_aia.name(row)
        if not path_lev1.exists():
            download(build_aia.url_base + row["path"], path_lev1)
            print(f"  {path_lev1.name}", flush=True)
        build_aia.check(row, path_lev1)
        return path_lev1

    # Downloaded in order of time, every channel of a slot before the next,
    # a few at once, and each registered while the next ones download.
    order = sorted(rows, key=lambda r: (r["T_REC"], int(r["WAVELNTH"])))
    with (
        concurrent.futures.ThreadPoolExecutor(num_downloads) as threads,
        concurrent.futures.ProcessPoolExecutor(num_workers) as executor,
    ):
        futures = dict()
        for path_lev1 in threads.map(fetch, order):
            path = directory_aia / name_cutout(path_lev1.name)
            if not path.exists():
                futures[executor.submit(cutout, path_lev1, path)] = path
        for future in concurrent.futures.as_completed(futures):
            future.result()
            print(f"  {futures[future].name}", flush=True)

    paths = []
    path_manifest = directory_aia / name_manifest
    with open(path_manifest, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            ("file", "record") + keys_aia + ("sha256", "lev1", "sha256_lev1")
        )
        for row in rows:
            path_lev1 = directory_lev1 / build_aia.name(row)
            path = directory_aia / name_cutout(path_lev1.name)
            h = header(path_lev1)
            record = f"{build_aia.series}[{row['T_REC']}][{row['WAVELNTH']}]"
            writer.writerow(
                (path.name, record)
                + tuple(h[k] for k in keys_aia)
                + (sha256(path), path_lev1.name, sha256(path_lev1))
            )
            paths.append(path)
    return [path_manifest] + paths


def build_xrt(directory: pathlib.Path) -> list[pathlib.Path]:
    """Download the XRT images and copy them into `directory`."""
    directory_xrt = directory / "xrt"
    directory_xrt.mkdir(parents=True, exist_ok=True)

    urls = hinode.xrt.urls(time_start_xrt, time_stop_xrt, filter=filter_xrt)
    files = hinode.xrt.download(urls)
    print(f"{urls.size} XRT images", flush=True)

    rows = []
    for i in urls.ndindex():
        url = str(urls[i].ndarray)
        file = pathlib.Path(files[i].ndarray)
        path = directory_xrt / file.name
        shutil.copyfile(file, path)
        h = astropy.io.fits.getheader(path, ext=0)
        rows.append((path.name, url) + tuple(h[k] for k in keys_xrt) + (sha256(path),))
    rows.sort(key=lambda r: r[2])

    path_manifest = directory_xrt / name_manifest
    with open(path_manifest, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("file", "url") + keys_xrt + ("sha256",))
        writer.writerows(rows)
    return [path_manifest] + [directory_xrt / r[0] for r in rows]


def build(directory: pathlib.Path) -> pathlib.Path:
    """Download the images into `directory` and pack them into an archive there."""
    paths = build_xrt(directory) + build_aia_cutouts(directory)

    path_archive = directory / name_archive
    with tarfile.open(path_archive, "w", format=tarfile.USTAR_FORMAT) as tar:
        for path in paths:
            arcname = path.relative_to(directory).as_posix()
            tar.add(path, arcname=arcname, filter=normalize)

    return path_archive


if __name__ == "__main__":
    path = build(pathlib.Path(sys.argv[1]))
    print(f"{path}\n    sha256  {sha256(path)}")

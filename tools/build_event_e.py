"""
Build the archive of the images of event E.

Event E is the jet at about (48, -88) arcseconds which ESIS observed during
its flight on 2019 September 30. The archive holds the images which the
article on event E uses. It inverts the differential emission measure (DEM)
of event E from 18:00 to 18:20 UTC, from when the jet begins to brighten in
X-rays to after it has faded, from:

- every Al_poly image of the X-Ray Telescope (XRT) on Hinode which began
  in that time, the Level 1 files of the Solar Data Analysis Center,
  unchanged;
- every image from seven EUV channels of the Atmospheric Imaging Assembly
  (AIA) on the Solar Dynamics Observatory in the JSOC's 12 second time slots
  from 17:59:36 to 18:20:36 UTC, which includes the image in each channel
  closest to the middle of every XRT exposure.
  The six channels of the DEM are there, and 304 Angstroms, which the
  article uses to co-align ESIS.

Beside them are:

- every line-of-sight magnetogram of the Helioseismic and Magnetic Imager
  (HMI) on the Solar Dynamics Observatory in the JSOC's 45 second time
  slots over the same 21 minutes;
- every 720 second line-of-sight magnetogram of HMI from 18:00 TAI on 2019
  September 29 to 20:00 TAI on September 30, from a day before event E to
  two hours after, for the history of the flux beneath it;
- the slit-jaw images at 1400 Angstroms of the observation of the Interface
  Region Imaging Spectrograph (IRIS) which spans the flight, the Level 2
  file of the Lockheed Martin Solar and Astrophysics Laboratory, unchanged.

The full-disk AIA images of those 21 minutes are about 6.6 GB, so the
archive keeps a cutout of each one, 400 pixels (240 arcseconds) on a side
around event E, after the image is registered with
:func:`sdo.aia.prep`, which rotates it to solar north up and scales it to
0.6 arcseconds per pixel.
Registration puts every image on the same grid, so the cutouts are taken at
the same coordinates in every image and share a grid too.
The data of each cutout is stored as 32-bit floating point, and its header
is the registered image's, with the reference pixel moved to the cutout.

The magnetograms are registered the same way, with
:func:`aiapy.calibrate.register`, and cut out the same size on the same
grid.
The 45 second magnetograms are cut out at the same coordinates as the AIA
images, so that their pixels are the same.
The 720 second magnetograms follow event E across the disk as the Sun
rotates: each is cut out around where the surface at the center of the AIA
cutouts at 18:10 UTC is at its own time, about 220 arcseconds further east
a day before.
The JSOC stores the magnetograms without their keywords, so the header of
each is made from the keywords the JSOC keeps for it before it is
registered.

Manifests record where each file came from, its time, channel or filter,
exposure, and the SHA-256 checksums of the file and, for AIA and HMI, of the
full-disk image it was cut from.

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
import re
import shutil
import sys
import tarfile
import typing
import warnings
import aiapy.calibrate
import astropy.coordinates
import astropy.io.fits
import astropy.time
import astropy.units as u
import astropy.wcs
import drms
import numpy as np
import named_arrays as na
import sunpy.coordinates
import sunpy.map
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

series_hmi = "hmi.M_45s"
"""The JSOC series of the magnetograms over the 21 minutes of the AIA images."""

series_history = "hmi.M_720s"
"""The JSOC series of the magnetograms of the history of the flux beneath event E."""

time_start_history = "2019.09.29_18:00:00_TAI"
"""The first time slot of the history, a day before event E."""

time_stop_history = "2019.09.30_20:00:00_TAI"
"""The last time slot of the history, two hours after event E."""

time_center = "2019-09-30T18:10:00Z"
"""
The time at which the surface which the cutouts of :data:`series_history`
follow is at :data:`center`, the middle of the XRT images.
"""

quality_hmi = 0x00010000
"""
The one bit of the QUALITY of a magnetogram which is allowed,
QUAL_LOWINTERPNUM. The daily calibrations of HMI at 06:00 and 18:00 UTC set
it, by leaving fewer filtergrams than usual to interpolate between.
"""

keys_hmi = ("T_REC", "T_OBS", "DATE-OBS", "QUALITY")
"""The keywords of each magnetogram copied into its manifest."""

url_iris = (
    "https://www.lmsal.com/solarsoft/irisa/data/level2_compressed/2019/09/30/"
    "20190930_171911_3604109624/"
    "iris_l2_20190930_171911_3604109624_SJI_1400_t000.fits.gz"
)
"""
Where the Lockheed Martin Solar and Astrophysics Laboratory serves the
Level 2 slit-jaw images at 1400 Angstroms of IRIS observation 3604109624,
from 17:19 to 18:28 UTC, which spans the flight.
"""

keys_iris = ("OBSID", "STARTOBS", "ENDOBS", "TDESC1", "EXPTIME", "CADEX_AV")
"""The keywords copied from the header of the IRIS file into its manifest."""

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


def query_hmi(record_set: str) -> list[dict[str, typing.Any]]:
    """
    Ask the JSOC for every keyword and for the path of each magnetogram in a
    record set.
    """
    keywords, segments = drms.Client().query(
        record_set,
        key="**ALL**",
        seg="magnetogram",
    )
    rows = []
    for i in range(len(keywords)):
        row = {k: keywords[k].iloc[i] for k in keywords.columns}
        row["path"] = str(segments["magnetogram"].iloc[i])
        rows.append(row)
    rows.sort(key=lambda r: r["T_REC"])
    return rows


def name_hmi(series: str, row: dict[str, typing.Any]) -> str:
    """
    The name of a full-disk magnetogram, after its series and time slot, as
    in ``hmi.m_45s.20190930_180000_TAI.magnetogram.fits``.
    """
    t_rec = str(row["T_REC"]).replace(".", "").replace(":", "")
    return f"{series.lower()}.{t_rec}.magnetogram.fits"


def name_cutout_hmi(name_full: str) -> str:
    """The name of the cutout of a full-disk magnetogram."""
    return name_full.replace(".magnetogram.fits", ".magnetogram_event_e.fits")


def header_hmi(row: dict[str, typing.Any]) -> astropy.io.fits.Header:
    """
    The header of a magnetogram, made from the keywords the JSOC keeps for
    it, since the file the JSOC stores holds none.

    The keywords without a value are left out, and so are those whose names
    FITS does not allow, which the JSOC adds to describe its time slots and
    to spell ``DATE-OBS`` a second time.
    """
    h = astropy.io.fits.Header()
    for k, v in row.items():
        if k == "path" or not re.fullmatch(r"[A-Z0-9_-]{1,8}", k):
            continue
        if isinstance(v, float) and np.isnan(v):
            continue
        h[k] = v.item() if isinstance(v, np.generic) else v
    return h


def check_hmi(row: dict[str, typing.Any]) -> None:
    """Check that no bit of the QUALITY of a magnetogram but :data:`quality_hmi` is set."""
    quality = int(row["QUALITY"])
    if quality & ~quality_hmi:
        raise ValueError(f"{row['T_REC']}: QUALITY is {quality:#010x}")


def center_history(frame: sunpy.coordinates.Helioprojective) -> u.Quantity:
    """
    Where the surface at :data:`center` at :data:`time_center` is seen in
    `frame`, carried there by the differential rotation of the Sun.
    """
    time = astropy.time.Time(time_center)
    position = astropy.coordinates.SkyCoord(
        *center,
        frame=sunpy.coordinates.Helioprojective(
            observer=sunpy.coordinates.get_earth(time),
            obstime=time,
        ),
    )
    with sunpy.coordinates.propagate_with_solar_surface():
        position = position.transform_to(frame)
    return u.Quantity([position.Tx, position.Ty]).to(u.arcsec)


def cutout_hmi(
    path_full: pathlib.Path,
    row: dict[str, typing.Any],
    path: pathlib.Path,
    track: bool,
) -> None:
    """
    Register one full-disk magnetogram and save the cutout around event E.

    Parameters
    ----------
    path_full
        The full-disk magnetogram the JSOC stores.
    row
        The keywords of the magnetogram, from :func:`query_hmi`.
    path
        Where to save the cutout.
    track
        Whether to cut out around :func:`center_history`, rather than
        around :data:`center`.
    """
    with astropy.io.fits.open(path_full, memmap=False) as hdul:
        data = hdul[1].data.astype(np.float32)
    magnetogram = sunpy.map.Map(data, header_hmi(row))
    with warnings.catch_warnings():
        # HMI calls its magnetograms Level 1.5, though they are not yet
        # rotated or scaled as the Level 1.5 images of aiapy are.
        warnings.filterwarnings(
            "ignore",
            message="Image registration should only be applied to level 1 data",
        )
        registered = aiapy.calibrate.register(magnetogram)

    h = registered.fits_header
    # The shape of the full-disk image, out of place, which astropy writes
    # again for the cutout.
    for k in ("SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "EXTEND"):
        h.remove(k, ignore_missing=True)
    h["MJD-OBS"] = astropy.time.Time(h["DATE-OBS"]).mjd
    wcs = astropy.wcs.WCS(h)

    middle = center_history(registered.coordinate_frame) if track else center
    corner = middle - num_pixel / 2 * 0.6 * u.arcsec
    x, y = wcs.world_to_pixel_values(
        corner[0].to_value(u.deg), corner[1].to_value(u.deg)
    )
    x0, y0 = int(np.rint(x)), int(np.rint(y))
    data = registered.data[y0 : y0 + num_pixel, x0 : x0 + num_pixel]
    data = data.astype(np.float32)
    if data.shape != (num_pixel, num_pixel):
        raise ValueError(f"{path_full.name}: the cutout leaves the image")

    h["CRPIX1"] = h["CRPIX1"] - x0
    h["CRPIX2"] = h["CRPIX2"] - y0
    h.remove("BLANK", ignore_missing=True)
    for package in ("aiapy", "sunpy"):
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


def build_hmi(
    directory: pathlib.Path,
    series: str,
    record_set: str,
    name_directory: str,
    track: bool,
) -> list[pathlib.Path]:
    """
    Download the magnetograms of a record set, register them, and save their
    cutouts.

    Parameters
    ----------
    directory
        The directory the archive is built in.
    series
        The JSOC series of the magnetograms.
    record_set
        The record set of the magnetograms, in JSOC notation.
    name_directory
        The directory of the archive the cutouts go in.
    track
        Whether the cutouts follow event E as the Sun rotates, with
        :func:`center_history`.
    """
    directory_full = directory / "hmi_full"
    directory_hmi = directory / name_directory
    directory_full.mkdir(parents=True, exist_ok=True)
    directory_hmi.mkdir(parents=True, exist_ok=True)

    rows = query_hmi(record_set)
    print(f"{len(rows)} magnetograms of {series}", flush=True)

    def fetch(row: dict[str, typing.Any]) -> tuple[pathlib.Path, dict[str, typing.Any]]:
        check_hmi(row)
        path_full = directory_full / name_hmi(series, row)
        if not path_full.exists():
            download(build_aia.url_base + str(row["path"]), path_full)
            print(f"  {path_full.name}", flush=True)
        return path_full, row

    with (
        concurrent.futures.ThreadPoolExecutor(num_downloads) as threads,
        concurrent.futures.ProcessPoolExecutor(num_workers) as executor,
    ):
        futures = dict()
        for path_full, row in threads.map(fetch, rows):
            path = directory_hmi / name_cutout_hmi(path_full.name)
            if not path.exists():
                future = executor.submit(cutout_hmi, path_full, row, path, track)
                futures[future] = path
        for future in concurrent.futures.as_completed(futures):
            future.result()
            print(f"  {futures[future].name}", flush=True)

    paths = []
    path_manifest = directory_hmi / name_manifest
    with open(path_manifest, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            ("file", "record") + keys_hmi + ("sha256", "full_disk", "sha256_full_disk")
        )
        for row in rows:
            path_full = directory_full / name_hmi(series, row)
            path = directory_hmi / name_cutout_hmi(path_full.name)
            writer.writerow(
                (path.name, f"{series}[{row['T_REC']}]")
                + tuple(row[k] for k in keys_hmi)
                + (sha256(path), path_full.name, sha256(path_full))
            )
            paths.append(path)
    return [path_manifest] + paths


def build_iris(directory: pathlib.Path) -> list[pathlib.Path]:
    """Download the IRIS slit-jaw images into `directory`."""
    directory_iris = directory / "iris"
    directory_iris.mkdir(parents=True, exist_ok=True)

    path = directory_iris / url_iris.rsplit("/", 1)[-1]
    if not path.exists():
        download(url_iris, path)
    print(f"  {path.name}", flush=True)
    h = astropy.io.fits.getheader(path, ext=0)

    path_manifest = directory_iris / name_manifest
    with open(path_manifest, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("file", "url") + keys_iris + ("sha256",))
        writer.writerow(
            (path.name, url_iris) + tuple(h[k] for k in keys_iris) + (sha256(path),)
        )
    return [path_manifest, path]


def build(directory: pathlib.Path) -> pathlib.Path:
    """Download the images into `directory` and pack them into an archive there."""
    paths = build_xrt(directory) + build_aia_cutouts(directory)
    paths += build_hmi(
        directory,
        series=series_hmi,
        record_set=f"{series_hmi}[{time_start_aia}/{duration_aia}]",
        name_directory="hmi",
        track=False,
    )
    paths += build_hmi(
        directory,
        series=series_history,
        record_set=f"{series_history}[{time_start_history}-{time_stop_history}]",
        name_directory="hmi_history",
        track=True,
    )
    paths += build_iris(directory)

    path_archive = directory / name_archive
    with tarfile.open(path_archive, "w", format=tarfile.USTAR_FORMAT) as tar:
        for path in paths:
            arcname = path.relative_to(directory).as_posix()
            tar.add(path, arcname=arcname, filter=normalize)

    return path_archive


if __name__ == "__main__":
    path = build(pathlib.Path(sys.argv[1]))
    print(f"{path}\n    sha256  {sha256(path)}")

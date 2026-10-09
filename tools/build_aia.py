"""
Build the archive of the AIA images taken while ESIS observed the Sun.

The archive holds every image from the 193 and 304 Angstrom channels of the
Atmospheric Imaging Assembly (AIA) on the Solar Dynamics Observatory in the
JSOC's time slots from 18:06 to 18:12 UTC on 2019 September 30. That spans the
Level-1 observations of ESIS (18:06:11.6 to 18:11:11.6 UTC) with a little to
spare.
These are the channels the ``esis`` package uses to synthesize a scene.

The images are the Level 1 files the JSOC (Joint Science Operations Center)
serves, unchanged, named the way the JSOC names the files it exports.
A manifest records the JSOC record, the time and exposure, the quality flag,
and the SHA-256 checksum of each one.

Run it as ``python tools/build_aia.py <directory>``. It downloads the images
into ``<directory>/aia`` and writes ``<directory>/esis-2019-aia-lev1.tar``,
whose contents and bytes depend only on the images.
"""

import csv
import hashlib
import pathlib
import sys
import tarfile
import time
import urllib.error
import urllib.request
import astropy.io.fits
import drms

series = "aia.lev1_euv_12s"
"""The JSOC series of the AIA Level 1 images from the EUV channels."""

time_start = "2019-09-30T18:06:00Z"
"""The first time slot of the archive."""

duration = "6m"
"""How long after :data:`time_start` the archive extends, in JSOC notation."""

channels = (193, 304)
"""The AIA channels in the archive, in Angstroms."""

name_archive = "esis-2019-aia-lev1.tar"
"""The name of the archive."""

name_manifest = "manifest.csv"
"""The name of the manifest inside the archive."""

url_base = "http://jsoc.stanford.edu"
"""The server which the paths the JSOC reports are relative to."""

keys = ("T_OBS", "DATE-OBS", "WAVELNTH", "EXPTIME", "QUALITY")
"""
The keywords copied from the header of each file into the manifest.

The header's own ``T_REC`` is left out. It is the time of the exposure rounded
to the second, not the 12 second slot of the record in :data:`series`.
"""

keys_check = ("T_OBS", "WAVELNTH")
"""The keywords checked against the JSOC's record of each file."""


def query() -> list[dict[str, str]]:
    """Ask the JSOC for the keywords and the path of each image."""
    channel = ",".join(str(c) for c in channels)
    record_set = f"{series}[{time_start}/{duration}][{channel}]"
    keys_query = ("T_REC",) + keys_check
    result, segments = drms.Client().query(
        record_set,
        key=",".join(keys_query),
        seg="image",
    )
    rows = []
    for i in range(len(result)):
        row = {k: str(result[k].iloc[i]) for k in keys_query}
        row["path"] = str(segments["image"].iloc[i])
        rows.append(row)
    return rows


def name(row: dict[str, str]) -> str:
    """The name the JSOC gives the image when it exports it."""
    t_rec = row["T_REC"].replace("-", "").replace(":", "")
    t_rec = f"{t_rec[:4]}-{t_rec[4:6]}-{t_rec[6:]}"
    return f"{series}.{t_rec}.{row['WAVELNTH']}.image_lev1.fits"


def download(url: str, path: pathlib.Path) -> None:
    """
    Download one file, waiting and trying again while the JSOC is busy.

    The JSOC refuses many requests at once with HTTP 503, so the files are
    downloaded one at a time. It has also answered with an empty file, so a
    download is kept only once it can be read as FITS, and it is written under
    another name until then.
    """
    path_partial = path.with_name(path.name + ".part")
    for attempt in range(10):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                content = response.read()
                size = int(response.headers["Content-Length"])
            if size == 0 or len(content) != size:
                raise OSError(f"got {len(content)} of {size} bytes of {url}")
            path_partial.write_bytes(content)
            header(path_partial)
            path_partial.replace(path)
            return
        except (urllib.error.URLError, OSError) as e:
            print(f"    {e}, trying again", flush=True)
            time.sleep(min(2**attempt, 300))
    raise RuntimeError(f"could not download {url}")


def header(path: pathlib.Path) -> astropy.io.fits.Header:
    """The header of the compressed image in an AIA Level 1 file."""
    return astropy.io.fits.getheader(path, ext=1)


def check(row: dict[str, str], path: pathlib.Path) -> None:
    """
    Check that a file holds the record the JSOC listed, and that no quality
    flag is set.
    """
    h = header(path)
    for k in keys_check:
        if str(h[k]) != row[k]:
            raise ValueError(f"{path.name}: {k} is {h[k]}, not {row[k]}")
    if h["QUALITY"] != 0:
        raise ValueError(f"{path.name}: QUALITY is {h['QUALITY']}")


def sha256(path: pathlib.Path) -> str:
    """The SHA-256 checksum of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Drop the owner and the time of each file so the archive is reproducible."""
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode = 0o644
    return info


def build(directory: pathlib.Path) -> pathlib.Path:
    """Download the images into `directory` and pack them into an archive there."""
    directory_aia = directory / "aia"
    directory_aia.mkdir(parents=True, exist_ok=True)

    rows = query()
    rows.sort(key=lambda r: (int(r["WAVELNTH"]), r["T_REC"]))
    print(f"{len(rows)} images", flush=True)

    for row in rows:
        path = directory_aia / name(row)
        if not path.exists():
            print(f"  {path.name}", flush=True)
            download(url_base + row["path"], path)
        check(row, path)

    path_manifest = directory_aia / name_manifest
    with open(path_manifest, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("file", "record") + keys + ("sha256",))
        for row in rows:
            path = directory_aia / name(row)
            h = header(path)
            record = f"{series}[{row['T_REC']}][{row['WAVELNTH']}]"
            writer.writerow(
                (path.name, record) + tuple(h[k] for k in keys) + (sha256(path),)
            )

    path_archive = directory / name_archive
    with tarfile.open(path_archive, "w", format=tarfile.USTAR_FORMAT) as tar:
        tar.add(path_manifest, arcname=name_manifest, filter=normalize)
        for row in rows:
            path = directory_aia / name(row)
            tar.add(path, arcname=path.name, filter=normalize)

    return path_archive


if __name__ == "__main__":
    path = build(pathlib.Path(sys.argv[1]))
    print(f"{path}\n    sha256  {sha256(path)}")

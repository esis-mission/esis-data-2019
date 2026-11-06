"""
Build the archive of our own measurements of the optics which flew in 2019.

The archive holds the final product of each measurement, the file exactly as
the software of the instrument wrote it, beside a manifest which records the
metadata of each file and its SHA-256 checksum. None of the intermediate
products the final ones were made from are kept.

So far that is the map of the figure of the primary mirror, which we measured
with a 4D Technology PhaseCam 6000 interferometer at the center of curvature
of the mirror, and saved with the interferometer's software, 4Sight, in its
HDF5 format.

Run it as ``python tools/build_metrology.py <source> <directory>``. It finds
each file listed in :data:`files` under ``<source>`` by its name, checks it
against its checksum, copies it into ``<directory>``, and writes
``<directory>/esis-2019-metrology.tar``, whose contents and bytes depend only
on the files.
"""

import csv
import dataclasses
import datetime
import hashlib
import pathlib
import shutil
import sys
import tarfile
import h5py


@dataclasses.dataclass(frozen=True)
class Measurement:
    """A file in the archive, and the optic it measures."""

    directory: str
    """The directory of the archive which holds the file."""

    name: str
    """The name of the file, as the software of the instrument saved it."""

    optic: str
    """The optic which was measured."""

    serial: str
    """The serial number of the optic."""

    sha256: str
    """The SHA-256 checksum of the file."""


files = (
    Measurement(
        directory="primary",
        name="PM_001_Figure_Promoted.h5",
        optic="primary mirror",
        serial="SN001",
        sha256="25b73f3d8c4b4917579c82371529760c4d2e05dee286ace0d700ff405c4abe2b",
    ),
)
"""The files in the archive."""

name_archive = "esis-2019-metrology.tar"
"""The name of the archive."""

name_manifest = "manifest.csv"
"""The name of the manifest in each directory of the archive."""

columns = (
    "file",
    "optic",
    "serial",
    "date",
    "software",
    "wavelength",
    "wedge",
    "height_units",
    "xpix",
    "sha256",
)
"""
The columns of each manifest.

The date is the one 4Sight recorded when it saved the file, in the local time
of the laboratory. The data of the file is a height in units of
``height_units`` of the ``wavelength``, multiplied by the ``wedge``, so a
wedge of 0.5 makes it the height of the surface, half the difference in the
optical path it measured. Its pixels are ``xpix`` apart on the surface.
"""


def sha256(path: pathlib.Path) -> str:
    """The SHA-256 checksum of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(value: bytes | str | float) -> str:
    """An attribute of an HDF5 file as text."""
    if isinstance(value, bytes):
        value = value.decode()
    return str(value).strip()


def metadata(path: pathlib.Path) -> dict[str, str]:
    """The metadata which 4Sight saved with a measurement, for its manifest."""
    with h5py.File(path, "r") as f:
        measurement = f["measurement0"]
        data = measurement["genraw"]
        date = datetime.datetime.strptime(
            text(measurement.attrs["date"]),
            "%a %b %d %H:%M:%S %Y",
        )
        return dict(
            date=date.isoformat(),
            software=f"4Sight {text(f['4D'].attrs['_4Sight_version'])}",
            wavelength=text(data.attrs["wavelength"]),
            wedge=text(data.attrs["wedge"]),
            height_units=text(data.attrs["height_units"]),
            xpix=text(data.attrs["xpix"]),
        )


def find(source: pathlib.Path, measurement: Measurement) -> pathlib.Path:
    """The one file under `source` with the name of `measurement`, checked against its checksum."""
    paths = sorted(source.rglob(measurement.name))
    if len(paths) != 1:
        raise FileNotFoundError(
            f"expected one {measurement.name} under {source}, found {len(paths)}"
        )
    path = paths[0]
    if sha256(path) != measurement.sha256:
        raise ValueError(f"{path} does not match its checksum")
    return path


def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Drop the owner and the time of each file so the archive is reproducible."""
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode = 0o644
    return info


def build(source: pathlib.Path, directory: pathlib.Path) -> pathlib.Path:
    """Copy the files from `source` into `directory` and pack them into an archive there."""
    directories = sorted({m.directory for m in files})

    for name in directories:
        path_directory = directory / name
        path_directory.mkdir(parents=True, exist_ok=True)
        measurements = [m for m in files if m.directory == name]
        for measurement in measurements:
            path = path_directory / measurement.name
            shutil.copyfile(find(source, measurement), path)
            if sha256(path) != measurement.sha256:
                raise ValueError(f"{path} does not match its checksum")

        with open(path_directory / name_manifest, "w", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(columns)
            for measurement in measurements:
                path = path_directory / measurement.name
                row = dict(
                    file=measurement.name,
                    optic=measurement.optic,
                    serial=measurement.serial,
                    sha256=measurement.sha256,
                    **metadata(path),
                )
                writer.writerow(tuple(row[c] for c in columns))

    path_archive = directory / name_archive
    with tarfile.open(path_archive, "w", format=tarfile.USTAR_FORMAT) as tar:
        for name in directories:
            path_directory = directory / name
            tar.add(
                path_directory / name_manifest,
                arcname=f"{name}/{name_manifest}",
                filter=normalize,
            )
            for measurement in files:
                if measurement.directory == name:
                    tar.add(
                        path_directory / measurement.name,
                        arcname=f"{name}/{measurement.name}",
                        filter=normalize,
                    )

    return path_archive


if __name__ == "__main__":
    path = build(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
    print(f"{path}\n    sha256  {sha256(path)}")

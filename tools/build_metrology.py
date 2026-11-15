"""
Build the archive of our own measurements of the optics which flew in 2019.

The archive holds the final product of each measurement, the file exactly as
the software of the instrument wrote it, beside a manifest which records the
metadata of each file and its SHA-256 checksum. None of the intermediate
products the final ones were made from are kept.

So far those are the map of the figure of the primary mirror and three maps
of each of the four gratings, which we measured with a 4D Technology PhaseCam
6000 interferometer at the center of curvature of each optic, and saved with
the interferometer's software, 4Sight, in its HDF5 format.

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
    Measurement(
        directory="gratings",
        name="EUV_014_Confocal_1.h5",
        optic="grating",
        serial="89027",
        sha256="f5afef823d11b7a2f5bb6b91e2896370fb85a5cd9000208b0396ae29561d18d7",
    ),
    Measurement(
        directory="gratings",
        name="EUV_014_Confocal_2.h5",
        optic="grating",
        serial="89027",
        sha256="d118345d9a4e427e58995ca57a4b56912b8b1a3785af012b8977ffb2d6ec222a",
    ),
    Measurement(
        directory="gratings",
        name="EUV_014_Confocal_3.h5",
        optic="grating",
        serial="89027",
        sha256="1f416af7c201ab04b8863b1d74b52c85a51339f505f7e76b8b3369bc9d466a07",
    ),
    Measurement(
        directory="gratings",
        name="EUV_017_Confocal_1.h5",
        optic="grating",
        serial="89024",
        sha256="2de596bc2e14356ec92550151e66bcb3d61a073d6ba85cc123540a65186ca645",
    ),
    Measurement(
        directory="gratings",
        name="EUV_017_Confocal_2.h5",
        optic="grating",
        serial="89024",
        sha256="aa7b631b46ea56aa36151540a1f32de51281e2a67214d825a94ec47858dd8e80",
    ),
    Measurement(
        directory="gratings",
        name="EUV_017_Confocal_3.h5",
        optic="grating",
        serial="89024",
        sha256="31d55e3cd3ef2be8a83d5a49b7b57e60b25d2b9bb4bcc477b259d484da4350c7",
    ),
    Measurement(
        directory="gratings",
        name="EUV_019_Confocal_1.h5",
        optic="grating",
        serial="89026",
        sha256="97a30ddcdf8d03801c5a8c51a6d58ea46835c372309e3791ea9056283356234d",
    ),
    Measurement(
        directory="gratings",
        name="EUV_019_Confocal_2.h5",
        optic="grating",
        serial="89026",
        sha256="bf504e1e384bbe0d9fac9b717ffd1392d511ea2dad91c222f0781d5c1b8283a5",
    ),
    Measurement(
        directory="gratings",
        name="EUV_019_Confocal_3.h5",
        optic="grating",
        serial="89026",
        sha256="495015a078352725faa522e68b3c90978ffbc776b2f62c19840ecc9ea0bc7096",
    ),
    Measurement(
        directory="gratings",
        name="EUV_024_Confocal_1.h5",
        optic="grating",
        serial="89025",
        sha256="dde1bbd52eb3ee67537161e9f3f375dd9d7162238a258b0d0f51ed1c4bc4e452",
    ),
    Measurement(
        directory="gratings",
        name="EUV_024_Confocal_2.h5",
        optic="grating",
        serial="89025",
        sha256="c1c38f34cc57fb05a110d4ea50a7eeba5b6b5639cc3ae4ab0c1c0298976ac854",
    ),
    Measurement(
        directory="gratings",
        name="EUV_024_Confocal_3.h5",
        optic="grating",
        serial="89025",
        sha256="bff131d25541de1933c9294eba777c1c0a4d06d88147af015da3f8b617bc577e",
    ),
)
"""
The files in the archive.

The maps of the gratings are named by the number of the blank each grating
was made on, UBO-16-014 for the grating with the serial number 89027 and so
on.
"""

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
optical path it measured, and a wedge of 1 leaves it that difference, twice
the height of the surface. Its pixels are ``xpix`` apart on the surface.
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

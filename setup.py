"""Build the ``pdphgs`` and ``pdprr`` binaries from pinned upstream sources
during ``pip install``.

Mirrors the shape of PyAILSII's setup.py (custom BuildPyCommand that
downloads an upstream tarball with verified SHA-256 and produces a compiled
binary inside the package dir), but the binaries are native C++ executables
produced by CMake + a C++ compiler instead of a JAR.

CMake and a C++17-capable compiler, plus Boost
(``program_options``, ``filesystem``, ``system``, ``regex``), are required at
build time when installing from sdist or running ``pip install -e .``.
End users of a prebuilt wheel need nothing — the wheels ship the compiled
binaries.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

from setuptools import Distribution, setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.develop import develop as _develop

# wheel.bdist_wheel was renamed to setuptools.command.bdist_wheel in
# setuptools 70 (June 2024). Prefer the new path, fall back for older
# setuptools where build-system.requires can't enforce it.
try:
    from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:  # setuptools < 70
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel  # type: ignore


# ---------------------------------------------------------------------------
# Upstream pinning. To bump:
#   1. Update UPSTREAM_SHA to the new commit
#   2. Re-download the tarball: curl -L "$URL" | shasum -a 256
#   3. Update UPSTREAM_TARBALL_SHA256
#   4. Run the full test suite — JSON-output format may have drifted
# ---------------------------------------------------------------------------
UPSTREAM_SHA = "451bc8a5d82cf5f7efd18f50cda3519d7232abbb"
UPSTREAM_TARBALL_SHA256 = (
    "e3f185c64e421deb368c810c5379dc8e091abee6bc65dacb999f32777b128e11"
)
UPSTREAM_URL = (
    f"https://github.com/vidalt/PDTSP/archive/{UPSTREAM_SHA}.tar.gz"
)

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE / "pdtsp"
BINARIES = ("pdphgs", "pdprr")


def _exe(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


def _require_toolchain() -> None:
    missing = []
    if shutil.which("cmake") is None:
        missing.append("cmake")
    # We don't probe for a specific compiler — CMake's project() will fail
    # with a clear message if no compiler is found, and the matrix of names
    # (cc, gcc, clang, cl) varies too much per platform to enumerate here.
    if missing:
        raise SystemExit(
            "PyPDTSP build requires CMake on PATH. "
            f"Missing: {', '.join(missing)}.\n"
            "  macOS:  brew install cmake boost\n"
            "  Debian: sudo apt install cmake g++ libboost-all-dev\n"
            "  RHEL:   sudo dnf install cmake gcc-c++ boost-devel\n"
            "  Windows: install CMake (https://cmake.org) and Boost via vcpkg.\n"
            "End users of a prebuilt wheel do not need a C++ toolchain; the "
            "toolchain is only required when building from sdist or "
            "`pip install -e .`."
        )


def _download_and_verify(url: str, dest: pathlib.Path, expected_sha256: str) -> None:
    print(f"PyPDTSP: downloading upstream sources from {url}")
    urllib.request.urlretrieve(url, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise SystemExit(
            "PyPDTSP: upstream tarball SHA256 mismatch.\n"
            f"  expected: {expected_sha256}\n"
            f"  got:      {digest}\n"
            "Refusing to build against unverified sources. If you intentionally "
            "bumped UPSTREAM_SHA, update UPSTREAM_TARBALL_SHA256 in setup.py."
        )


def _patch_grubhub_reader(instancereader: pathlib.Path) -> None:
    """Patch a nullptr-deref bug in upstream's Grubhub instance reader.

    Upstream ``PDP-HGS/pdp/instancereader.cpp::InstanceReaderGrubhub::fromFile``
    (line 137 at SHA ``451bc8a5``) reads::

        double**& distances = Application::instance->Distances();

    but ``Application::instance`` isn't assigned until *after* this function
    returns (see ``PDP-HGS/main.cpp`` around line 40). Dereferencing the
    null pointer makes ``pdphgs --grubhub`` segfault on every distance-matrix
    input. The local variable ``instance`` (defined two lines earlier)
    points to the same object once construction returns, so swapping the
    qualifier fixes the crash without changing semantics.

    Filed upstream is on the backlog; meanwhile we patch in-place.
    """
    text = instancereader.read_text()
    bug = "double**& distances = Application::instance->Distances();"
    fix = "double**& distances = instance->Distances();"
    if bug not in text:
        print(
            "PyPDTSP: warning — Grubhub nullptr-deref pattern not found in "
            "instancereader.cpp. Upstream may have fixed it; the patcher is "
            "now a no-op."
        )
        return
    instancereader.write_text(text.replace(bug, fix))


def _patch_cmakelists(cmakelists: pathlib.Path) -> None:
    """Patch upstream ``CMakeLists.txt`` so the binaries we build are both
    portable and compatible with modern CMake / Boost.

    Two changes:

    1. **Strip ``-march=native``** — upstream sets this for benchmark speed,
       but it produces binaries that crash with ``SIGILL`` on older CPUs in
       the manylinux / macOS / Windows fleet we ship wheels to. The cost is
       a few percent of throughput; the win is binaries that actually run.

    2. **Rewrite the Boost link section to use imported targets**
       (``Boost::program_options`` etc.) instead of the legacy
       ``${Boost_LIBRARIES}`` variable. Modern Boost (1.70+) ships
       ``BoostConfig.cmake``, which doesn't always populate
       ``Boost_LIBRARIES``; the legacy ``FindBoost`` module is on a removal
       path (CMake policy CMP0167). Imported targets work with both the new
       and the legacy machinery and have been stable since Boost 1.55.

       Without this patch, ``find_package(Boost COMPONENTS ...)`` succeeds
       but ``target_link_libraries(... ${Boost_LIBRARIES})`` resolves to an
       empty link line, and linking fails with thousands of "undefined
       symbol" errors against ``boost::program_options::``.
    """
    text = cmakelists.read_text()
    patched = text.replace(" -march=native", "")
    if patched == text:
        print(
            "PyPDTSP: warning — '-march=native' was not present in "
            "CMakeLists.txt; upstream layout may have changed."
        )

    boost_block = (
        "find_package(Boost COMPONENTS program_options filesystem system regex)\n"
        "if (Boost_FOUND)\n"
        "    include_directories(${Boost_INCLUDE_DIRS})\n"
        "\n"
        "    target_link_libraries(pdphgs ${Boost_LIBRARIES})\n"
        "    target_link_libraries(pdprr ${Boost_LIBRARIES})\n"
        "endif ()\n"
    )
    # Use the umbrella `find_package(Boost ...)` with `Boost::<comp>`
    # imported targets:
    #
    # * Works with **legacy FindBoost.cmake** (Boost < 1.70, e.g.
    #   AlmaLinux 8's Boost 1.66 in manylinux_2_28 — `dnf install
    #   boost-devel`) which provides imported targets but no
    #   per-component config files.
    # * Works with **modern BoostConfig.cmake** (Boost ≥ 1.70, e.g.
    #   brew on macOS, apt on Ubuntu 24.04) — CMake's `find_package`
    #   falls through from MODULE to CONFIG mode automatically when no
    #   explicit CONFIG keyword is given.
    # * `OPTIONAL_COMPONENTS system` + `$<TARGET_NAME_IF_EXISTS:...>`
    #   handles the fact that `boost_system` has been header-only since
    #   Boost 1.69, so modern packages don't ship a separate `Boost::system`
    #   library/target.
    #
    # Per-component CONFIG mode (the earlier attempt) was abandoned
    # because (a) AlmaLinux 8's Boost 1.66 has no per-component configs
    # — they were introduced in Boost 1.70 — and (b) vcpkg's static-md
    # Boost on Windows doesn't reliably ship them either.
    boost_block_replacement = (
        "find_package(Boost REQUIRED COMPONENTS program_options filesystem regex "
        "OPTIONAL_COMPONENTS system)\n"
        "set(_pdtsp_boost_libs\n"
        "    Boost::program_options Boost::filesystem Boost::regex\n"
        "    $<TARGET_NAME_IF_EXISTS:Boost::system>)\n"
        "target_link_libraries(pdphgs ${_pdtsp_boost_libs})\n"
        "target_link_libraries(pdprr ${_pdtsp_boost_libs})\n"
    )
    if boost_block in patched:
        patched = patched.replace(boost_block, boost_block_replacement)
    else:
        print(
            "PyPDTSP: warning — Boost link block in CMakeLists.txt did not "
            "match the expected upstream text; the build may fail at link "
            "time. Inspect the upstream CMakeLists.txt and update "
            "_patch_cmakelists in setup.py."
        )

    cmakelists.write_text(patched)


def _build_binaries() -> None:
    # Idempotent: if both binaries already exist, trust them. This makes
    # repeated `pip install -e .` invocations cheap.
    if all((PKG / _exe(name)).is_file() for name in BINARIES):
        print("PyPDTSP: binaries already present in pdtsp/, skipping build.")
        return

    _require_toolchain()

    with tempfile.TemporaryDirectory(prefix="pdtsp-build-") as td_str:
        td = pathlib.Path(td_str)
        tarball = td / "upstream.tar.gz"
        _download_and_verify(UPSTREAM_URL, tarball, UPSTREAM_TARBALL_SHA256)

        print("PyPDTSP: extracting upstream tarball")
        with tarfile.open(tarball, "r:gz") as tf:
            # `filter='data'` is the safe extraction default starting in
            # Python 3.14. Pass it when available (3.12+); on older Pythons
            # the kwarg doesn't exist and would raise TypeError.
            if sys.version_info >= (3, 12):
                tf.extractall(td, filter="data")
            else:
                tf.extractall(td)
        try:
            extracted = next(td.glob("PDTSP-*"))
        except StopIteration:
            raise SystemExit(
                "PyPDTSP: could not locate extracted upstream directory"
            )
        if not (extracted / "CMakeLists.txt").is_file():
            raise SystemExit(
                f"PyPDTSP: missing CMakeLists.txt in upstream tarball "
                f"({extracted})"
            )

        _patch_cmakelists(extracted / "CMakeLists.txt")
        _patch_grubhub_reader(
            extracted / "PDP-HGS" / "pdp" / "instancereader.cpp"
        )

        build_dir = td / "build"
        build_dir.mkdir()

        configure_argv = [
            "cmake",
            "-S", str(extracted),
            "-B", str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
        ]
        # Propagate the cibuildwheel-supplied vcpkg toolchain on Windows;
        # this lets find_package(Boost ...) locate the components vcpkg
        # installed in the before-all hook.
        if "CMAKE_TOOLCHAIN_FILE" in os.environ:
            configure_argv.append(
                f"-DCMAKE_TOOLCHAIN_FILE={os.environ['CMAKE_TOOLCHAIN_FILE']}"
            )
        # On macOS, honor cibuildwheel's ARCHFLAGS so universal2 / arm64
        # wheels produce the right binary. ARCHFLAGS looks like
        # "-arch x86_64 -arch arm64"; we map it to CMAKE_OSX_ARCHITECTURES.
        if platform.system() == "Darwin":
            tokens = os.environ.get("ARCHFLAGS", "").split()
            archs = [tokens[i + 1] for i, t in enumerate(tokens)
                     if t == "-arch" and i + 1 < len(tokens)]
            if archs:
                configure_argv.append(
                    f"-DCMAKE_OSX_ARCHITECTURES={';'.join(archs)}"
                )
        print("PyPDTSP: configuring with", " ".join(configure_argv))
        subprocess.run(configure_argv, check=True)

        build_argv = [
            "cmake", "--build", str(build_dir),
            "--config", "Release",
            "--parallel",
        ]
        print("PyPDTSP: building with", " ".join(build_argv))
        subprocess.run(build_argv, check=True)

        # Locate the produced binaries. CMakeLists.txt sets
        # EXECUTABLE_OUTPUT_PATH=./ so single-config generators (Makefiles,
        # Ninja) drop them directly in the build root. Multi-config
        # generators (MSVC, Xcode) drop them in build/Release/.
        candidates = [build_dir, build_dir / "Release"]
        PKG.mkdir(parents=True, exist_ok=True)
        for name in BINARIES:
            exe = _exe(name)
            src = next(
                (c / exe for c in candidates if (c / exe).is_file()),
                None,
            )
            if src is None:
                searched = ", ".join(str(c / exe) for c in candidates)
                raise SystemExit(
                    f"PyPDTSP: built binary {exe!r} not found. "
                    f"Searched: {searched}"
                )
            dest = PKG / exe
            shutil.copy2(src, dest)
            if platform.system() != "Windows":
                dest.chmod(0o755)
            print(f"PyPDTSP: wrote {dest} ({dest.stat().st_size} bytes)")


class BuildPyCommand(_build_py):
    def run(self):
        _build_binaries()
        super().run()


class DevelopCommand(_develop):
    def run(self):
        _build_binaries()
        super().run()


class BdistWheelPlatformSpecific(_bdist_wheel):
    """Mark the wheel as platform-specific even though we have no
    `setuptools.Extension` modules.

    Combined with ``BinaryDistribution.has_ext_modules() → True``
    below, this puts the native binaries (`pdphgs`, `pdprr`) directly
    under ``pdtsp/`` in the wheel (platlib root) instead of the default
    ``pdtsp-0.1.0.data/purelib/pdtsp/`` location, which is what
    ``auditwheel repair`` (Linux) and ``delocate-wheel`` (macOS) expect
    for binary content. Without this, both repair tools reject the
    wheel ("Invalid binary wheel, found shared library in purelib").

    The wheel tag also moves from ``py3-none-any`` to a platform-
    specific tag (e.g. ``cp313-cp313-macosx_15_0_arm64``), which
    cibuildwheel 3.x requires (it errors on ``py3-none-any``).
    """

    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False


class BinaryDistribution(Distribution):
    """Tell setuptools this distribution contains platform-specific
    binaries even though it has no `setuptools.Extension` modules.

    The native executables (`pdphgs`, `pdprr`) are shipped via
    ``package_data`` and invoked through ``subprocess``, so they're
    not technically C extensions — but they ARE platform-specific.
    setuptools doesn't notice that on its own; this `distclass`
    override is the canonical idiom for the case (see the
    `auditwheel`/`delocate` user guides, and packages like
    `cmake`-installed-via-pip).

    Without this override, setuptools routes package_data files into
    the wheel's ``purelib/`` data dir, and the repair tools refuse
    to process them.
    """

    def has_ext_modules(self):  # noqa: D401
        return True


setup(
    cmdclass={
        "build_py": BuildPyCommand,
        "develop": DevelopCommand,
        "bdist_wheel": BdistWheelPlatformSpecific,
    },
    distclass=BinaryDistribution,
)

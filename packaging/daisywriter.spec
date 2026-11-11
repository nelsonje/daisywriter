# PyInstaller build: one folder with two programs sharing the same libraries.
#   daisywriter(.exe)      the window (no console)
#   daisywriter-cli(.exe)  the command line
# Build:  uv run --group packaging pyinstaller packaging/daisywriter.spec --noconfirm
# Output: dist/daisywriter/      (the WiX installer packs this folder; see daisywriter.wxs)
#         dist/daisywriter.app   on macOS, with both programs in Contents/MacOS (see make_dmg.sh)
import os
import sys
from importlib.metadata import version

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

here = SPECPATH  # noqa: F821 - defined by PyInstaller
mac = sys.platform == "darwin"
icon = os.path.join(here, "daisywriter.icns" if mac else "daisywriter.ico")  # make_icon.py draws them
binaries = collect_dynamic_libs("libusb_package") if mac else []  # libusb, so the app needs no Homebrew
datas = collect_data_files("daisywriter") + collect_data_files("docx")  # profiles; Word's default template
hidden = ["daisywriter.gui", "daisywriter.gui.main_window", "daisywriter.transports.usbprint",
          "daisywriter.transports.file", "daisywriter.transports.emulator"]
excludes = ["tkinter", "pytest", "hypothesis"]


def analysis(script):
    # python-docx finds its templates through paths like docx/parts/../templates, so its
    # modules must be real files on disk, not entries in the archive
    return Analysis([os.path.join(here, script)], datas=datas, binaries=binaries,  # noqa: F821
                    hiddenimports=hidden,
                    excludes=excludes, module_collection_mode={"docx": "py"})


gui, cli = analysis("daisywriter_gui.py"), analysis("daisywriter_cli.py")
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="daisywriter",  # noqa: F821
              console=False, upx=False, icon=icon)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="daisywriter-cli",  # noqa: F821
              console=True, upx=False, icon=icon)
coll = COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas,  # noqa: F821
               name="daisywriter", upx=False)
if mac:
    BUNDLE(coll, name="daisywriter.app", icon=icon, bundle_identifier="io.github.nelsonje.daisywriter",  # noqa: F821
           version=version("daisywriter"),
           info_plist={"CFBundleName": "daisywriter", "CFBundleDisplayName": "daisywriter",
                       "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "12.0",
                       "NSHumanReadableCopyright": "MIT License"})

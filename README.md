# daisywriter
Tools for printing to daisywheel typewriters: mail merge from a Word template
and an Excel spreadsheet onto a typewriter, one typed letter per row.

**Using daisywriter:** download it from **https://daisywriter.jfet.net**, which
also has the [user guide](src/daisywriter/gui/user_guide.md) (in the app under
Help, too). Every release, with its installers for Windows and Mac and the sample
letters, is on the [Releases](https://github.com/nelsonje/daisywriter/releases) page.

For the design and roadmap, see [docs/PLAN.md](docs/PLAN.md); to make a release,
[docs/releases](docs/releases/README.md).

## Status
Phases 1, 2, 3 and 5 are done: read the template and spreadsheet, validate
the merge, re-wrap the letters to the typewriter's margins, add typing errors
with typewriter-style corrections if wanted, preview them, and print them from
macOS (tested on the Swintec 1146 CMP) or on an emulated typewriter, from the
command line or the window. Printing from Windows (phase 4) and the Windows
installer (phase 6) are written and tested in CI, but not yet with the
typewriter.

## Install on Windows
Download the `.msi` from the [latest release](https://github.com/nelsonje/daisywriter/releases)
(or, for a development build, the `daisywriter-msi` artifact of a CI run) and run it. It installs
daisywriter for all users (Windows asks for permission, and warns that the
publisher is unknown because the installer isn't signed yet), adds daisywriter
to the Start menu, and puts `daisywriter-cli` on the PATH for the command line.
Uninstall it from Settings > Apps.

To build it yourself on Windows:
```sh
uv sync --group packaging
uv run --group packaging pyinstaller packaging/daisywriter.spec --noconfirm
dotnet tool install --global wix --version 5.0.2
wix build packaging/daisywriter.wxs -arch x64 -wx -bindpath app=<full path to dist\daisywriter> -bindpath <full path to packaging> -d Version=0.1.0 -o daisywriter.msi
```

## Install on a Mac
Download the `.dmg` for Apple-silicon Macs from the latest release (or the
`daisywriter-dmg` artifact of a CI run), open it and drag daisywriter to
Applications. The app isn't signed yet, so the first time macOS refuses to open
it: open it once, then go to System Settings > Privacy & Security and choose
Open Anyway. libusb comes inside the app; nothing else needs installing.

For the command line, link it onto your PATH:
```sh
sudo ln -s /Applications/daisywriter.app/Contents/MacOS/daisywriter-cli /usr/local/bin/daisywriter-cli
```
To build it yourself: `uv run --group packaging pyinstaller packaging/daisywriter.spec --noconfirm`,
then `packaging/make_dmg.sh`.

## Try it
```sh
uv sync
uv run daisywriter gui                             # the window (also: daisywriter-gui)
uv run daisywriter make-samples samples           # prototype template + spreadsheet
uv run daisywriter validate samples/letter-template.docx samples/letter-data.xlsx
uv run daisywriter preview  samples/letter-template.docx samples/letter-data.xlsx --letters 1-2
uv run daisywriter preview  samples/letter-template.docx samples/letter-data.xlsx -o preview.html
uv run daisywriter profiles
```
Printing needs a USB printer-class parallel adapter. On macOS and Linux it needs libusb (e.g. `brew install libusb`); on Windows the built-in USB Printing Support driver is used, so nothing needs installing (no printer has to be set up either):
```sh
uv run daisywriter status                          # is the typewriter connected and on-line? (exit 1 if not)
uv run daisywriter probe                           # how far ahead of the typewriter the adapter takes data
uv run daisywriter testpage margins format bold    # calibration patterns
uv run daisywriter print samples/letter-template.docx samples/letter-data.xlsx --letters 1
uv run daisywriter print ... --dry-run out.bin     # write the bytes to a file instead
uv run daisywriter print ... --emulate out.pdf     # type on an emulated typewriter; draw the sheets
uv run daisywriter print ... --typing-errors 2      # about 2 corrected typing errors per 100 words
```
Before each page, insert a sheet until the rollers above the printing point catch it, with
the typewriter ON LINE. daisywriter feeds to the 1-inch top margin, types the page, then
rolls the sheet out.

Useful options: `--profile olympia-electronic-compact-2`, `--today 2026-11-08`,
`--page-numbers after-first --page-number-format "{{LastName}} - Page {page} - {{Today}}"`,
`--no-justify`, `--top`/`--bottom` (lines), `--stock letter|legal|a4`.

## Writing a template
- Merge fields: Word's own **Insert Merge Field**, or typed `{{FieldName}}` / `«FieldName»`.
  Field names match column headers ignoring case, spaces and underscores.
- Values are typed **as they appear in Excel**: format the column in Excel (Currency, Date,
  Zip Code, ...) and the letter follows. No formatting in the template is needed.
- Optionally, a format in the template overrides Excel's: `{{OrderDate:MMMM d, yyyy}}`,
  `{{Amount:$#,##0.00}}`, or Word field switches (`\@`, `\#`). `{{LastName:Upper}}` changes
  case. `--ignore-excel-formats` turns Excel formats off.
- `{{Today}}` or a Word DATE field gives the print date ("November 8, 2026" unless formatted).
- Bold, underline, strikethrough (overtyped with hyphens), alignment (including justify), and indents are typed; fonts and sizes are
  ignored. Lines are re-wrapped to the typewriter's margins; only paragraph breaks and
  Shift+Enter line breaks are kept.
- A line made only of blank fields (an empty `Address2`, say) is left out.
- The letter body (for simulated typing errors, later) is found between "Dear ...," and the
  closing ("Sincerely,"), or set explicitly with `{{body}}` ... `{{/body}}`.
- Page headers/footers are ignored (letterhead is assumed pre-printed).

## Development
```sh
git config user.email jacob@jfet.net   # this project's commits use this email
git config core.hooksPath .githooks    # once per clone: refuse commits and pushes with any other
uv run pytest
uv run ruff check src tests
uv run python website/build.py --out _site   # the web page (published by .github/workflows/pages.yml)
```
CI also fails if any commit carries another email (the `emails` job).

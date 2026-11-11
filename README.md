# daisywriter
Tools for printing to daisywheel typewriters: mail merge from a Word template
and an Excel spreadsheet onto a typewriter, one typed letter per row.

See [docs/PLAN.md](docs/PLAN.md) for the design and roadmap.

## Status
Phases 1, 2, 3 and 5 are done: read the template and spreadsheet, validate
the merge, re-wrap the letters to the typewriter's margins, add typing errors
with typewriter-style corrections if wanted, preview them, and print them from
macOS (tested on the Swintec 1146 CMP) or on an emulated typewriter, from the
command line or the window. Next: printing from Windows (phase 4) and the
installer (phase 6).

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
Printing (macOS/Linux with a USB printer-class parallel adapter; needs libusb, e.g. `brew install libusb`):
```sh
uv run daisywriter status                          # is the typewriter connected and on-line?
uv run daisywriter testpage margins format bold    # calibration patterns
uv run daisywriter print samples/letter-template.docx samples/letter-data.xlsx --letters 1
uv run daisywriter print ... --dry-run out.bin     # write the bytes to a file instead
uv run daisywriter print ... --emulate out.pdf     # type on an emulated typewriter; draw the sheets
uv run daisywriter print ... --typing-errors 2      # about 2 corrected typing errors per 100 words
```
Before each page, insert a sheet until the rollers above the printing point catch it, with
the typewriter ON LINE. daisywriter feeds to the 1-inch top margin, types the page, then
rolls the sheet out.

Useful options: `--profile olympia-compact-2`, `--today 2026-11-08`,
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
uv run pytest
uv run ruff check src tests
```

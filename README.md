# daisywriter
Tools for printing to daisywheel typewriters: mail merge from a Word template
and an Excel spreadsheet onto a typewriter, one typed letter per row.

See [docs/PLAN.md](docs/PLAN.md) for the design and roadmap.

## Status
Phase 1 (no hardware yet): read the template and spreadsheet, validate the
merge, re-wrap the letters to the typewriter's margins, and preview them.
Printing comes in phase 2.

## Try it
```sh
uv sync
uv run daisywriter make-samples samples           # prototype template + spreadsheet
uv run daisywriter validate samples/letter-template.docx samples/letter-data.xlsx
uv run daisywriter preview  samples/letter-template.docx samples/letter-data.xlsx --letters 1-2
uv run daisywriter preview  samples/letter-template.docx samples/letter-data.xlsx -o preview.html
uv run daisywriter profiles
```
Useful options: `--profile olympia-compact-2`, `--today 2026-11-08`,
`--page-numbers after-first --page-number-format "{{LastName}} - Page {page} - {{Today}}"`,
`--no-justify`, `--top`/`--bottom` (lines), `--stock letter|legal|a4`.

## Writing a template
- Merge fields: Word's own **Insert Merge Field**, or typed `{{FieldName}}` / `«FieldName»`.
  Field names match column headers ignoring case, spaces and underscores.
- Formats: `{{OrderDate:MMMM d, yyyy}}`, `{{Amount:$#,##0.00}}`, `{{LastName:Upper}}`,
  or Word field switches (`\@`, `\#`, `\*`). Dates default to "November 8, 2026".
  `{{Today}}` or a Word DATE field gives the print date.
- Bold, underline, alignment (including justify), and indents are typed; fonts and sizes are
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

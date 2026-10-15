# Sensor 78 calculation workbook

Open [Sensor78_Emission_Comparison_Simple.xlsx](Sensor78_Emission_Comparison_Simple.xlsx) in Excel. All traffic inputs, emission rates, calibrated parameters, calculation formulas, and saved calculation results are embedded; the workbook does not load external files.

## Read the workbook

| Sheets | Purpose |
|---|---|
| **01 Traffic inputs** | Editable traffic inputs, prepared five-minute counts and speeds, and numerical integration settings. |
| **02 Emission rates** | Speed/VSP lookup boundaries and four pollutant rates. |
| **03 Recorded O** | Detector-speed reference calculation. |
| **04 Mean speed S** | Single observed mean speed; inherits observed total travel time. |
| **05 Reconstructed R** | Fitted delay curve, reconstructed speeds, and count-preserving five-minute alignment. |
| **06 Two-speed M** | Free-flow/queue travel times with lookup emission rates. |
| **07 Cubic A** | Same two travel-time components with cubic emission rates. |
| **08 Results** | Episode totals, comparison errors, and consistency checks. |

This is one fixed January average-weekday example: detector 78, 16 complete weekdays, 57 five-minute bins from 14:45 to 19:30. It is separate from the pooled 137-episode analysis. Five-minute emissions assign the full-link emissions of the counted vehicles to their count intervals; they are not exhaust physically released during those exact clock intervals. O is a modeled detector-speed reference, not measured emissions.

Yellow cells are editable inputs. Changing inputs recalculates the fixed example; it does not redetect episodes or refit the traffic calibration. The A-method cubic coefficients remain separately supplied inputs and must be refitted if the emission-rate scenario changes.

## Files and evidence

| File | What it provides |
|---|---|
| [scripts/build_simple_sensor78.mjs](scripts/build_simple_sensor78.mjs) | Original workbook-generation source, including formulas and formatting instructions; see the layout note below. |
| [scripts/audit_simple_workbook.py](scripts/audit_simple_workbook.py) | Read-only comparison of cached results with the independent Python reference, plus formula/error/external-link checks. Requires `openpyxl`. |
| [scripts/validate_simple_excel.ps1](scripts/validate_simple_excel.ps1) | Optional native Excel recalculation, input perturbations, restoration, save/reopen checks. Runs on a separate copy using Windows and installed desktop Excel. |
| [scripts/prepare_public_workbook.py](scripts/prepare_public_workbook.py) | Removes optional local-directory metadata when publishing an Excel-saved workbook; does not rewrite any worksheet or calculation payload. |
| [audits/current_workbook_audit.json](audits/current_workbook_audit.json) | Fresh read-only audit of this published copy. |
| [audits/simple_workbook_audit.json](audits/simple_workbook_audit.json) | Original independent audit, before publication metadata was removed. |
| [audits/native_excel_validation.json](audits/native_excel_validation.json) | Original native Excel recalculation and four input-perturbation checks. |
| [audits/publication_metadata_audit.json](audits/publication_metadata_audit.json) | Source/published hashes and confirmation that all worksheet/formula/cache/style entries are unchanged. |

The checked workbook has eight sheets, 14,446 formulas, no missing cached formula values, no formula errors, and no external workbook/data dependencies. Its 20 method-by-pollutant totals match the independent reference within the recorded numerical tolerance. The only change made to the supplied current workbook for publication is removal of Excel's optional local folder metadata. The archived native Excel evidence is retained separately from the fresh read-only audit; native recalculation was not rerun during publication.

**Layout note:** the current workbook has more compact O and S sheets than the original generator. Their five-minute data begin at rows 11 and 9, respectively; the generator places both at row 24. The published workbook preserves the current layout, while running the original generator recreates its earlier layout. The audit locates table headings and checks all 57 rows without assuming those original row positions. All 20 current totals match the numerical reference.

## Reproduce or audit

Run the following commands from the repository root. The prepared numerical payload is [../results/simple_workbook_inputs.json](../results/simple_workbook_inputs.json); its generator and upstream data are documented in [../README.md](../README.md).

```text
python debug/sensor78/workbook/scripts/audit_simple_workbook.py
```

The audit writes to `debug/output/sensor78/workbook/current_workbook_audit.json`. Override `--workbook`, `--inputs`, or `--report` to check a regenerated copy. A fresh Python audit reads saved values; it does not itself recalculate Excel formulas.

Output-path guards reject collisions with inputs and reject writes anywhere in the repository outside `debug/output/`, including published references, reports, and source code. Write regenerated files and new audit reports to `debug/output/` or an external working directory. The archived audit records in this folder remain unchanged.

To generate a fresh workbook:

```text
node debug/sensor78/workbook/scripts/build_simple_sensor78.mjs
```

**Generation requires the Codex-provided `@oai/artifact-tool` Node runtime.** That dependency is not bundled here, and the generator is not claimed to run in an ordinary public Node installation. The existing workbook can be used in Excel without that runtime. The builder defaults to `debug/output/sensor78/workbook/`, with optional positional arguments for input JSON and output XLSX; it leaves the published workbook unchanged.

For optional native Excel validation on Windows:

```powershell
powershell -File debug/sensor78/workbook/scripts/validate_simple_excel.ps1
```

This creates a separate workbook in `debug/output/sensor78/workbook/`, changes and restores four representative inputs, and saves a JSON record. It requires installed Microsoft Excel and the ability to automate it through COM. Pass `-WorkbookPath` to check a regenerated workbook and `-OutputDirectory` to choose a fresh working directory. The validation script exits with an error if restored/reopened results differ from baseline, formula errors or external dependencies are found, or the traffic model is not valid. The comparison uses all 40 displayed result values and an absolute tolerance of `1e-8`. Existing validation output files and reparse-point output ancestors are rejected to protect earlier evidence and reference files.

The archived native Excel checks were performed for the saved source workbook. The additional failure assertions and path guards were syntax-reviewed during publication, but native Excel was not rerun for those changes.

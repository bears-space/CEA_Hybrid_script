# CEA Hybrid Script

This project runs NASA CEA-based performance calculations for a hybrid rocket concept using nitrous oxide oxidizer, a paraffin surrogate fuel, and an ABS surrogate blend. The script sweeps oxidizer-to-fuel ratio and nozzle expansion ratio values and reports the best-performing cases for each ABS fraction.

## What It Does

- Evaluates hybrid rocket performance with the `cea` Python package
- Sweeps across user-defined `O/F` and `Ae/At` values
- Compares several ABS volume fractions in the fuel blend
- Prints key outputs such as `Isp`, `Cf`, mass flow, chamber temperature, and nozzle dimensions

## Project Files

- `main.py`: main analysis script
- `inputs.json`: intended input configuration file
- `test.py`: small direct CEA sanity check

## Requirements

- Python 3
- Installed `cea` package
- `numpy`

If you use the included virtual environment, activate it before running the script.

## How To Use

1. Adjust the input values in `main.py` for thrust, chamber pressure, `Ae/At`, `O/F`, and ABS fractions.
2. Run the main script:

```powershell
python main.py
```

3. Review the printed output in the terminal.

## Notes

- The ABS chemistry is modeled with a simplified styrene/butadiene surrogate.
- Density values and mixture shares are first-pass engineering assumptions.
- Results depend on the species definitions available in the installed CEA database.

Recorded REAL data (2026-09-21, read-only, zero-cost): Virtuoso's netlist export of
`GPDK045_RINGOSC/tb_ring_osc_3stage` and the CDF readbacks of `ring_osc_3stage` and its testbench, exactly as the
workbench's `import_cell` reader stored them. A plain 3-stage CMOS ring oscillator with MIM load capacitors on the
generic GPDK045. Used as the fixture of `test_wb_profiles.py`; nothing here is simulated.

`core_cdf.json` (2026-09-22, read-only, zero-cost): what the property form of every instance of `ring_osc_3stage` lets a
user type - the `cdf_facts` query of the `import_cell` reader, parsed: the CDF of `nmos1v`, `pmos1v` and `mimcap` (form
fields, rules, callbacks, choices, form procedures, Spectre entries) and each instance's form rules evaluated on it.
Used by `test_wb_cdf_write.py`.

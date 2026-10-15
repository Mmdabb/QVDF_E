# Data notice

The authors make **no claim** on the data in this folder. The MIT License of the code does not apply here. The data are shared for research use and remain subject to the terms of their original providers:

| Data | Provider and terms |
| --- | --- |
| Arizona I-10 detector records and everything derived from them (`inputs/empirical/source_files/arizona_i10`, Arizona rows of `inputs/empirical/baseline`, `inputs/detector78`, `frozen/calibration`, `frozen/transitions/corridor`, `examples/`) | Legacy Arizona Department of Transportation (ADOT) loop-detector data, cleaned, synchronized and post-processed for Zhou et al. (2022), *Multimodal Transportation* 1, 100017. The supplied lane-speed and lane-volume input files are included for research reproducibility; no official ADOT release is implied. Contact ADOT for any other use |
| California profiles (`inputs/empirical/source_files/pems`, PeMS rows of `inputs/empirical/baseline` and `frozen/calibration`) | Caltrans Performance Measurement System, via the released profiles at https://github.com/jacky850/pems-cbi-dv. PeMS terms of use apply |
| Platoon-transition records (`frozen/transitions/ks1_*`) | Derived from trajectories provided by Prof. Rui Jiang's group, Beijing Jiaotong University. The raw trajectories are not redistributed |
| Emission rates (`frozen/calibration/emission_input`, cubic fits) | Derived from the U.S. EPA MOVES model; the original run settings were not recorded |

If you use these data, cite the paper and the original sources above.

The input bundle's inventory, hashes and source mappings are in `inputs/README.md`, `inputs/MANIFEST_SHA256.json` and `inputs/provenance.json`. Including these files does not place the underlying data under the code's MIT License. Raw platoon trajectories and the missing original MOVES RunSpec are not included.

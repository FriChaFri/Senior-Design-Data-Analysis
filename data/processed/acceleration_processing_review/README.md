# Acceleration Processing Review

These outputs explain how the gameplay acceleration signal is cleaned before it is used for battery sizing.

## Processing steps

1. Load the cleaned gameplay CSV and resample it to a uniform sample rate.
2. Convert user acceleration from g to m/s^2.
3. Use the gravity vector to remove the vertical component and keep horizontal motion.
4. Estimate a dominant forward axis and project the 3-axis motion onto that signed direction.
5. Winsorize extreme outliers at a high percentile to reduce the influence of isolated spikes.
6. Low-pass filter to remove very fast jitter that does not represent wheelchair-scale motion.
7. Remove slow bias drift with a centered rolling median.
8. Clip acceleration above the realistic threshold to limit likely collision-like spikes.
9. Integrate the final acceleration into a bounded surrogate speed for downstream force and power modeling.

## Assumptions used

- resample_hz: 100.0
- winsor_percentile: 99.9
- lowpass_cutoff_hz: 0.5
- lowpass_order: 4
- bias_window_s: 20.0
- v_max_m_s: 4.91744
- representative_minutes: 60.0
- session_hours: 2.0
- forward_axis_override: None
- use_acceleration_magnitude: False
- max_realistic_accel_m_s2: 2.85

## Per-game folders

Each game folder contains:
- `sensor_context.png`: raw axes, gravity, horizontal-only motion, and forward-axis projection
- `pipeline_overview.png`: the full signal-cleaning pipeline and before/after comparisons
- `event_windows.png`: zoomed views of the strongest positive and negative events

A machine-readable summary was also written to `data/processed/acceleration_processing_review/processing_summary.csv`.

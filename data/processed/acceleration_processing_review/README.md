# Propulsion Processing Review

These plots explain the current planar, yaw-aware gameplay pipeline used for wheelchair propulsion sizing.

Important limitation: the cleaned gameplay CSVs currently present in this workspace do not include `motionRotationRate*` columns, so these review plots can validate impact handling and planar propulsion demand, but they cannot validate turning from this dataset alone.

## Current flow

1. Load the cleaned gameplay CSV and resample it to a uniform time base.
2. Convert user acceleration from g to m/s^2.
3. Align the average gravity direction to vertical and keep only court-plane motion.
4. Detect impact-like events from planar acceleration magnitude and jerk, then interpolate across those windows.
5. Winsorize and low-pass filter the planar acceleration and yaw-rate traces.
6. Remove slow planar drift with a rolling median bias estimate.
7. Clip only the final propulsion-demand magnitude to the realistic acceleration cap.
8. Integrate planar acceleration into planar velocity with zero-velocity resets during stationary windows.
9. Use yaw rate plus speed to split demand into left/right wheel speeds for turning-aware sizing.

## Files

- `summary_dashboard.png`: cross-game overview of impacts, propulsion peaks, yaw peaks, and speed peaks
- `<game>/sensor_context.png`: raw phone signals, gravity alignment, planar motion, and yaw rate
- `<game>/pipeline_overview.png`: impact repair, smoothing, clipping, speed, and wheel-speed split
- `<game>/event_windows.png`: zoomed windows for impact, propulsion, and turning events

## Assumptions used

- resample_hz: 100.0
- winsor_percentile: 99.5
- lowpass_cutoff_hz: 0.5
- lowpass_order: 4
- bias_window_s: 8.0
- linear_lowpass_cutoff_hz: 1.25
- yaw_lowpass_cutoff_hz: 1.5
- v_max_m_s: 6.0
- representative_minutes: 60.0
- session_hours: 2.0
- max_realistic_accel_m_s2: 2.85
- impact_accel_threshold_m_s2: 25.0
- impact_jerk_threshold_m_s3: 120.0
- impact_padding_s: 0.35
- stationary_accel_threshold_m_s2: 0.2
- stationary_yaw_rate_threshold_rad_s: 0.2
- stationary_hold_s: 0.35
- velocity_decay_tau_s: 8.0
- wheel_track_m: 0.68
- yaw_inertia_kg_m2: 10.0

Machine-readable summary: `data/processed/acceleration_processing_review/processing_summary.csv`

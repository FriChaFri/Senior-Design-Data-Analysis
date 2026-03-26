# Powered Sports Wheelchair Motion-to-Battery Experiment Report

## Executive Summary

This project set out to answer a practical senior design question: can we take real upper-body gameplay motion, map it through a physics-based drivetrain model, and use that to estimate whether a lean-controlled powered sports wheelchair is realistic from a battery and motor standpoint?

The short answer is yes, but only after being careful about what the IMU data means physically.

The main findings were:

- The motion-history-to-power approach is viable and much better than guessing battery size first.
- Raw IMU peaks from body-mounted data can wildly overstate propulsion demand if they are treated as direct chair acceleration.
- A clipped, signed acceleration model with a realism cap of `±2.85 m/s²` produced much more believable results.
- Under that clipped model, the chosen `450 W` planetary motor family with `16:1` gearing is much more plausible than it first appeared.
- Battery voltage does not materially change required power or energy, but it strongly changes pack current.
- The second, lower-rate dataset validated the overall direction of the results: once aggressive clipping is applied, the peak design point becomes stable across both recordings.

This report documents the full experiment, including the processing workflow, mathematical model, mistakes we discovered, what changed as assumptions improved, and what the current results imply for design decisions.

## 1. Project Goal

The design goal was to build a powered sports wheelchair controlled by upper-body lean so the user’s hands stay free for sports. The chair should feel athletic and responsive, not like a generic slow mobility device.

The engineering question behind this report was:

> Given measured IMU motion from real gameplay, what battery, motor, torque, current, and power would be required for a powered chair to reproduce a similar motion profile?

The team specifically wanted the sizing path to begin from motion and work forward:

```text
acceleration history -> speed history -> force -> wheel torque -> motor torque/current
-> electrical power -> battery energy / capacity
```

## 2. Data Sources

Two independent measurement sets were used.

### Dataset A: Charles phone data

These were the original higher-rate gameplay recordings that were cleaned into:

- [Game1CharlesPhone_clean.csv](../clean_games/Game1CharlesPhone_clean.csv)
- [Game2CharlesPhone_clean.csv](../clean_games/Game2CharlesPhone_clean.csv)

These files contain:

- timestamped samples
- user acceleration channels
- gravity channels
- gyroscope / motion channels

These became the main source of the early analysis work.

### Dataset B: Caleb phone data

A second lower-rate recording captured the same games in one HyperIMU export:

- [BothGamesCalebPhone.csv](/home/chafri/Documents/seniorDesign/data/raw/BothGamesCalebPhone.csv)

This file required special handling because:

- it had metadata headers, not a standard CSV header in line 1
- it had no explicit timestamp per sample
- both games were combined into one file
- it sampled at `100 ms`, or about `10 Hz`

It was reconstructed and split into:

- [Game1CalebPhone_clean.csv](../clean_games_caleb/Game1CalebPhone_clean.csv)
- [Game2CalebPhone_clean.csv](../clean_games_caleb/Game2CalebPhone_clean.csv)

The comparison report for the second dataset is here:

- [second_dataset_report.md](../second_dataset_report/second_dataset_report.md)

## 3. Experimental Workflow

The analysis evolved in stages.

### Stage 1: Clean and inspect the gameplay data

The first step was to isolate the gameplay windows from the raw phone recordings. That produced the cleaned Charles files and the initial review figures.

Useful review outputs:

- [Game1 acceleration review](../acceleration_review/Game1CharlesPhone_clean_acceleration_review.png)
- [Game2 acceleration review](../acceleration_review/Game2CharlesPhone_clean_acceleration_review.png)
- [Filter / clip comparison](../acceleration_review/filter_clip_comparison.png)

### Stage 2: Build a first-pass battery sizing model

The first pass tried to map cleaned IMU motion directly into:

- traction force
- wheel torque
- motor torque/current
- battery power
- session energy

This experiment included battery chemistry assumptions and a battery-mass feedback loop.

Outputs:

- [scenario_summary.csv](../battery_sizing/scenario_summary.csv)
- [Game1 battery plot](../battery_sizing/plots/Game1CharlesPhone_battery_sizing.png)
- [Game2 battery plot](../battery_sizing/plots/Game2CharlesPhone_battery_sizing.png)

### Stage 3: Challenge the raw IMU interpretation

During review, a major issue emerged:

- some high acceleration spikes were likely not propulsion at all
- some very large negative spikes likely came from hard stops, collisions, or abrupt contact
- treating acceleration magnitude as direct chair demand was too aggressive

This led to a more careful interpretation:

- signed acceleration should be preserved
- unrealistic peaks should be clipped
- propulsion sizing and crash/contact interpretation should not be treated as the same thing

### Stage 4: Fix the realism problem with clipping

After discussion, the team chose:

- peak realistic acceleration limit: `2.85 m/s²`

The revised rule was:

- signed acceleration above `+2.85 m/s²` is not trusted as realistic propulsion
- signed acceleration below `-2.85 m/s²` is not trusted as realistic in-chair deceleration
- the analysis should use the clipped signal instead of raw spikes

### Stage 5: Motor and voltage sweep

The selected concept motor was tested with:

- `16:1` planetary gearing
- `11.75 in` wheel radius
- `105 kg` total system mass
- `Crr = 0.002`
- wheel rotational inertia `J = 0.2 kg·m²` per driven wheel
- two-wheel drive

Voltage was then treated as a sweep variable rather than a fixed assumption.

Outputs:

- [motor_requirement_summary.csv](../motor_requirements/motor_requirement_summary.csv)
- [run_motor_requirement_analysis.py](/home/chafri/Documents/seniorDesign/scripts/run_motor_requirement_analysis.py)

### Stage 6: Validate against the second dataset

The lower-rate HyperIMU recording was processed with the same clipping rule and compared against the original Charles-based analysis.

Comparison figures:

- [Trace comparison](../second_dataset_report/figures/trace_comparison.png)
- [Distribution comparison](../second_dataset_report/figures/distribution_comparison.png)
- [Voltage sweep current](../second_dataset_report/figures/voltage_sweep_current.png)
- [Peak load comparison](../second_dataset_report/figures/peak_load_comparison.png)

## 4. Mathematical Model

This section documents the model used by the scripts, along with the logic behind it.

### 4.1 Signal preprocessing

The phone IMU does not directly give forward wheelchair acceleration. The first processing step was:

1. resample the signal to a uniform timeline
2. convert linear acceleration to SI units
3. use gravity information to separate vertical and horizontal motion
4. construct a signed acceleration demand signal
5. low-pass filter it
6. subtract slow bias
7. clip unrealistic peaks

Conceptually:

```text
a_raw(t) -> a_filtered(t) -> a_clipped(t)
```

For the final clipped runs:

```text
a_clipped(t) = clip(a_filtered(t), -2.85, +2.85)
```

### 4.2 Speed estimate

Speed was estimated by discrete integration with a hard cap:

```text
v[k+1] = clip(v[k] + a[k] * dt, 0, v_max)
```

with:

- `v_max = 11 mph`

This was not treated as a ground-truth wheel-speed measurement. It was a bounded surrogate speed for power estimation.

### 4.3 Longitudinal force model

The forward traction force was modeled as:

```text
F_trac = m a + F_rr + F_drag + F_grade
```

with:

```text
F_rr = C_rr m g
F_drag = 0.5 rho C_d A v^2
F_grade = 0
```

for the flat-ground cases used here.

### 4.4 Wheel torque with rotational inertia

The wheel torque model included both linear acceleration demand and wheel inertia:

```text
tau_wheel,total = r * F_trac + N_driven * J * (a / r)
```

where:

- `r` is wheel radius
- `J` is wheel rotational inertia per driven wheel
- `N_driven = 2`

Per-wheel torque was:

```text
tau_wheel,per = tau_wheel,total / 2
```

### 4.5 Motor torque and current

With gear ratio `G` and gearbox efficiency `eta_g`:

```text
tau_motor = tau_wheel,per / (G * eta_g)
I_motor = tau_motor / K_t
```

### 4.6 Electrical power and battery current

The simplified electrical path was:

```text
P_elec = P_wheel / eta_drive + P_aux
```

Then candidate pack voltage only changed current:

```text
I_pack = P_elec / V_pack
```

This is why voltage sweep matters: it does not change required power much, but it changes how much current the pack and controller must deliver.

### 4.7 Earlier battery chemistry sizing path

Before the clipped-motor study, the project also explored battery chemistry and mass assumptions. That earlier branch estimated:

- usable Wh
- nominal Wh
- Ah at pack voltage
- battery mass
- peak battery C-rate

The chemistry families tested were:

- `NMC`
- `LiFePO4`
- `SLA`

That work is still useful because it showed which chemistries look reasonable from an energy / mass standpoint even before the motor model was fully refined.

## 5. Important Problems We Discovered

This project became much better once the team treated it like an experiment and not a one-pass calculation.

### Problem 1: Raw body-mounted IMU is not the same as wheel acceleration

The phone was under the player’s leg. That means the signal includes:

- real whole-body movement
- local body dynamics
- impacts
- possible hard stops from contact

The result is that raw spikes can exaggerate propulsion demand.

### Problem 2: Signed acceleration matters

Using pure acceleration magnitude hides the difference between:

- forward drive demand
- braking
- contact / collision stops

That is why the later analysis moved back toward signed acceleration plus clipping.

### Problem 3: Second dataset format mismatch

The lower-rate HyperIMU export had:

- metadata headers
- no standard timestamp column
- a different sensor naming scheme
- both games in a single file

This required a custom loader and a new split process before the same analysis could be applied.

### Problem 4: Peak demand is far more sensitive than average demand

Small changes in how the acceleration peaks are interpreted produce large changes in:

- peak torque
- peak current
- peak power

That is exactly why the clipping rule changed the design picture so much.

## 6. Results

### 6.1 What the early battery chemistry study showed

From the first battery sweep, the main ranges were:

- usable energy: about `564 Wh` to `774 Wh`
- nominal energy: about `626 Wh` to `1290 Wh`
- battery mass: about `3.9 kg` to `36.9 kg`
- peak motor current: about `58 A` to `112 A`
- peak battery C-rate: about `4.5 C` to `7.7 C`

Interpretation:

- `NMC` looked attractive on mass
- `LiFePO4` looked heavier but still plausible
- `SLA` looked impractical for a sports chair because mass became extremely large

This was an important discovery even before the final clipped motor model:

> The project did not look energy-limited first. It looked peak-demand-limited first.

### 6.2 What the clipped motor study showed

At the final clipped design point, the current Charles-based 48 V results were:

- session energy: about `372 Wh` to `415 Wh`
- peak electrical power: about `2.02 kW`
- peak pack current at `48 V`: about `42.1 A`
- peak wheel torque per motor: about `47.9 Nm`
- required peak motor torque: about `3.32 Nm`
- required peak motor current: about `27.24 A`

These values came from:

- total system mass `105 kg`
- wheel radius `11.75 in`
- `16:1` gearing
- `Crr = 0.002`
- `J = 0.2 kg·m²`
- clipped acceleration ceiling `±2.85 m/s²`

This was a major shift from the earlier unbounded interpretation of the data.

### 6.3 Voltage sweep

At the clipped design point, the peak electrical power stayed essentially fixed while pack current changed with voltage:

- `24 V`: about `84.2 A`
- `36 V`: about `56.1 A`
- `48 V`: about `42.1 A`
- `60 V`: about `33.7 A`
- `72 V`: about `28.1 A`

The engineering lesson is straightforward:

> Higher voltage is a current-management tool, not a free reduction in required power.

### 6.4 Lower-rate dataset validation

At `48 V`, the second dataset gave:

- `Game1Caleb`: about `288 Wh`, `42.1 A`, `47.9 Nm/wheel`
- `Game2Caleb`: about `291 Wh`, `42.1 A`, `47.9 Nm/wheel`

compared with:

- `Game1Charles`: about `415 Wh`, `42.1 A`, `47.9 Nm/wheel`
- `Game2Charles`: about `372 Wh`, `42.1 A`, `47.9 Nm/wheel`

This tells us two things:

1. Once clipping is applied, the peak design point is stable across both datasets.
2. The lower-rate dataset predicts lower session energy because it smooths or misses short-duration activity.

That is exactly the kind of cross-check we wanted from the second recording.

## 7. What We Learned

The most important discoveries from the experiment were:

- A real-data-driven sizing approach is feasible and useful.
- The quality of the preprocessing assumptions matters as much as the force equations.
- Signed acceleration is more informative than raw magnitude for propulsion analysis.
- Clipping unrealistic spikes is not a cosmetic choice; it changes the design conclusion.
- The selected `450 W` motor family with `16:1` gearing looks much more realistic under the clipped model than under the raw-spike model.
- Battery voltage should be treated as a design sweep because current changes substantially with voltage.
- The lower-rate dataset supports the clipped model by showing that the peak design point is not just a single-device artifact.

## 8. Current Design Interpretation

At this point, the project does **not** look obviously impossible from a battery standpoint.

The present interpretation is:

- Energy requirement is moderate under the clipped model.
- Peak electrical power is nontrivial but manageable.
- `48 V` looks reasonable, though higher voltages would lower pack current further.
- `NMC` and `LiFePO4` remain much more realistic than `SLA` for an athletic chair.
- The chosen motor concept is now plausible enough to keep studying, rather than being immediately ruled out.

The main uncertainty is no longer “does the math exist?” It is:

- how closely the clipped IMU signal represents true in-chair propulsion demand
- how trustworthy the motor’s real peak torque and controller behavior will be in hardware

## 9. Limitations

This work still has important limitations.

- The IMU is body-mounted, not wheel-mounted.
- The surrogate speed is modeled, not measured.
- The motor/controller torque-speed curve is not fully known.
- The gearbox efficiency is still an assumption.
- The second dataset’s Game 2 recording ends earlier than the Charles clean window.
- Impacts and propulsion are still separated by heuristics, not by direct labeled ground truth.

These limitations do not invalidate the work, but they should be stated clearly.

## 10. Recommended Next Steps

The most useful next steps would be:

1. Measure actual wheel speed or wheel RPM during gameplay.
2. Obtain a real torque-speed-current curve for the motor/controller pair.
3. Separate propulsion events and impact events more explicitly.
4. Repeat the experiment with the chair or a test rig instead of only body-mounted motion.
5. Decide whether the design target should be:
   - the clipped data profile
   - the lower-rate profile
   - or a deliberately conservative design envelope above both

## 11. Key Files Produced During This Experiment

### Reports

- [overall_experiment_report.md](./overall_experiment_report.md)
- [second_dataset_report.md](../second_dataset_report/second_dataset_report.md)

### Summary tables

- [scenario_summary.csv](../battery_sizing/scenario_summary.csv)
- [motor_requirement_summary.csv](../motor_requirements/motor_requirement_summary.csv)
- [second_dataset_summary.csv](../second_dataset_report/second_dataset_summary.csv)

### Important figures

- [Game1 acceleration review](../acceleration_review/Game1CharlesPhone_clean_acceleration_review.png)
- [Game2 acceleration review](../acceleration_review/Game2CharlesPhone_clean_acceleration_review.png)
- [Trace comparison](../second_dataset_report/figures/trace_comparison.png)
- [Distribution comparison](../second_dataset_report/figures/distribution_comparison.png)
- [Voltage sweep current](../second_dataset_report/figures/voltage_sweep_current.png)
- [Peak load comparison](../second_dataset_report/figures/peak_load_comparison.png)

## Closing Note

This project improved because the team kept challenging its own assumptions.

The final outcome was not just a battery number. It was a better experimental process:

- collect real motion
- translate it into physics
- inspect where the interpretation breaks
- refine the assumptions
- compare against a second dataset
- and only then make design claims

That is exactly the kind of reasoning a senior design experiment should demonstrate.

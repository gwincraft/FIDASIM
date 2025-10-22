title: Neutron Collimation

[TOC]

---

# Neutron Collimation Diagnostic

The neutron collimation (NC) diagnostic in FIDASIM provides comprehensive modeling of collimated neutron detection systems used to diagnose fast-ion populations in fusion plasmas. This diagnostic is particularly valuable for studying energetic deuterium ions through their neutron-producing DD fusion reactions.

## Overview

Neutron collimators measure neutrons born from D-D fusion reactions in the plasma with spatial and energy resolution. Unlike passive neutron detectors that integrate signal from the entire plasma, collimated systems use apertures to define sightlines, enabling spatially localized measurements. The NC diagnostic in FIDASIM calculates:

1. **Weight Functions**: Phase-space sensitivity W(E, pitch, channel) describing how each diagnostic channel responds to fast-ions at different energies and pitch angles
2. **Neutron Flux**: Channel-resolved energy-dependent neutron flux reaching each detector
3. **Spatial Emissivity**: Optional channel-resolved neutron emissivity maps on the R-Z grid

These calculations enable forward modeling of expected neutron signals from theoretical fast-ion distributions and support inverse techniques like velocity-space tomography.

## Physical Basis

### DD Fusion Reactions

The D-D fusion reaction has two equally probable branches:

$$
\text{D} + \text{D} \rightarrow \text{n} (2.45\text{ MeV}) + {}^3\text{He} (0.82\text{ MeV}) \quad [50\%]
$$

$$
\text{D} + \text{D} \rightarrow \text{p} (3.02\text{ MeV}) + \text{T} (1.01\text{ MeV}) \quad [50\%]
$$

The neutron-producing branch (branch 2 in the code) has a Q-value of 3.27 MeV. FIDASIM focuses on this neutron-producing channel for NC diagnostics.

### Neutron Production Mechanisms

FIDASIM considers two neutron production mechanisms:

**1. Beam-Thermal (BT) Reactions**

Fast deuterium ions from neutral beam injection interact with thermal deuterium in the plasma:

$$
\text{D}_{\text{fast}} + \text{D}_{\text{thermal}} \rightarrow \text{n} + {}^3\text{He}
$$

This is the dominant contribution for energetic fast-ion populations and is the primary signal for diagnosing the fast-ion distribution.

**2. Thermal-Thermal (TT) Reactions**

Thermal deuterium ions colliding with each other:

$$
\text{D}_{\text{thermal}} + \text{D}_{\text{thermal}} \rightarrow \text{n} + {}^3\text{He}
$$

This provides a background signal that depends on plasma temperature and thermal deuterium density. While less important for fast-ion diagnostics, it contributes to the overall neutron flux.

### Reaction Rate Calculation

The DD reaction rate is calculated using pre-tabulated rates based on Bosch-Hale cross-section parameterizations. The subroutine `get_dd_rate` (src/fidasim.f90:9525) interpolates these tables as a function of:

- Beam energy $E_b$ (or relative energy in the center-of-mass frame)
- Plasma ion temperature $T_i$

The reaction rate has units of [1/s] and represents the number of reactions per fast-ion per second at a given position in the plasma. The rate depends on:

$$
\text{Rate} = n_{\text{thermal}} \langle \sigma v \rangle(E_b, T_i)
$$

where:
- $n_{\text{thermal}}$ is the thermal deuterium density [cm⁻³]
- $\langle \sigma v \rangle$ is the velocity-averaged cross-section [cm³/s]

The code accounts for plasma rotation by calculating the effective beam energy:

$$
E_{\text{rel}} = \frac{1}{2} m_{\text{beam}} |\vec{v}_{\text{beam}} - \vec{v}_{\text{rot}}|^2
$$

This ensures accurate reaction rates in rotating plasmas where the relative velocity differs from the lab-frame beam velocity.

## Neutron Kinematics

### Energy Calculation

The neutron energy in the laboratory frame depends on the kinematics of the DD reaction and is calculated using relativistic two-body kinematics in `get_dd_neutron_energy` (src/fidasim.f90:9754).

**Center-of-Mass Frame**

First, the center-of-mass (CM) velocity is calculated:

$$
\vec{v}_{\text{CM}} = \frac{\vec{v}_1 + \vec{v}_2}{2}
$$

where $\vec{v}_1$ is the fast-ion velocity and $\vec{v}_2$ is the thermal ion velocity.

The relative velocity is:

$$
\vec{v}_{\text{rel}} = \vec{v}_1 - \vec{v}_2
$$

The total energy available in the CM frame is:

$$
E_{\text{CM,total}} = \frac{1}{2}\mu v_{\text{rel}}^2 + Q
$$

where $\mu = m_D/2$ is the reduced mass for the D-D system and $Q = 3.27$ MeV is the Q-value.

**Energy Distribution**

In the CM frame, energy is partitioned between products by momentum and energy conservation. For the neutron:

$$
E_{\text{CM,n}} = \frac{m_{^3\text{He}}}{m_n + m_{^3\text{He}}} E_{\text{CM,total}} \approx 0.75 \times E_{\text{CM,total}}
$$

This gives the neutron approximately 75% of the available kinetic energy in the CM frame.

**Lorentz Boost to Lab Frame**

The neutron energy in the laboratory frame requires a Lorentz boost:

$$
E_{\text{lab,n}} = E_{\text{CM,n}} + E_{\text{boost}} + 2\sqrt{E_{\text{CM,n}} E_{\text{boost}}} \cos\theta
$$

where:
- $E_{\text{boost}} = \frac{1}{2}m_n v_{\text{CM}}^2$ is the kinetic energy due to CM motion
- $\theta$ is the angle between the CM velocity and the detector direction

This formulation properly accounts for the Doppler shift of neutron energies due to the bulk motion of the reacting ions, which is crucial for accurate neutron spectroscopy.

### Angular Distribution and Anisotropy

DD neutron emission is **not isotropic** in the center-of-mass frame, particularly at higher beam energies. The angular distribution is described by a Legendre polynomial expansion:

$$
\frac{d\sigma}{d\Omega} = a_0 + a_2 P_2(\cos\theta) + a_4 P_4(\cos\theta)
$$

where $P_2$ and $P_4$ are Legendre polynomials and $a_0$, $a_2$, $a_4$ are energy-dependent coefficients.

#### Anisotropy Correction Factor

The subroutine `get_ddnhe_anisotropy` (src/fidasim.f90:9675) implements this correction based on experimental data from Brown & Jarmie [NIM A236 (1985) 380]. Key features:

1. **Energy Dependence**: Coefficients $a_0(E)$, $a_2(E)$, $a_4(E)$ are interpolated from tabulated values measured at beam energies from 10-117 keV (center-of-mass)

2. **Angle Calculation**: The code calculates $\cos\theta$ in the CM frame using:
   - The transformation from lab to CM frame
   - The detector sightline direction
   - Proper handling of the kinematic parameter $k_0$

3. **Normalization**: The anisotropy factor $\kappa$ is normalized such that:

$$
\kappa = \frac{a_i + b_i\cos^2\theta + c_i\cos^4\theta}{a_i + b_i/3 + c_i/5}
$$

where the denominator ensures proper normalization when integrated over solid angle.

4. **Bosch-Hale Consistency**: Correction factors are applied to make the tabulated anisotropy coefficients consistent with the Bosch-Hale reaction rate parameterization.

This anisotropy correction is **critical** for accurate neutron collimator simulations because:
- Forward-going neutrons (in the direction of fast-ion motion) are enhanced
- Backward-going neutrons are suppressed
- The effect becomes more pronounced at higher energies
- Ignoring this effect can lead to errors of 20-50% in predicted signals

## Neutron Collimator Geometry

### Geometric Configuration

Each neutron collimator channel is defined by two geometric elements:

1. **Aperture**: A front collimating aperture that defines the field of view
2. **Detector**: A rear neutron detector element

Both elements are specified by:
- Center position (3D coordinates)
- Radial and toroidal edge vectors defining size and orientation
- Shape (rectangular or circular)

The geometry is read from the HDF5 input file by `read_neutron_collimator` (src/fidasim.f90:3318).

### Coordinate System

Input geometry is specified in a UVW coordinate system and converted to the beam grid XYZ coordinate system. The aperture and detector positions define the sightline centerline for each channel.

For each channel, the code constructs:

```
Detector Origin → defines starting point for ray tracing
Aperture Origin → defines sightline direction
```

The sightline unit vector is:

$$
\hat{v}_n = \frac{\vec{r}_{\text{aperture}} - \vec{r}_{\text{detector}}}{|\vec{r}_{\text{aperture}} - \vec{r}_{\text{detector}}|}
$$

### Shape Support

Both rectangular (shape=1) and circular (shape=2) detector and aperture geometries are supported. The solid angle calculation differs:

**Rectangular**:
$$
d\Omega = \frac{h_h \times h_w}{\pi d^2}
$$

**Circular**:
$$
d\Omega = \frac{h_h \times h_w}{4 d^2}
$$

where $h_h$ and $h_w$ are half-height and half-width (or related radial dimensions), and $d$ is the distance from the emission point to the detector.

## Weight Function Calculation

Weight functions describe the phase-space sensitivity of each diagnostic channel. They answer the question: "How sensitive is this channel to a fast-ion at energy $E$ and pitch $p$ at various locations in the plasma?"

### Mathematical Definition

The neutron collimator weight function is defined as:

$$
W(E, p, \text{chan}) \equiv \frac{\text{d}\Phi_n}{\text{d}F(E,p) \, \text{d}E \, \text{d}p}
$$

where:
- $\Phi_n$ is the neutron flux at the detector [neutrons/s]
- $F(E,p)$ is the fast-ion distribution function [ions/(cm³ keV)]
- $E$ is the fast-ion energy
- $p$ is the pitch angle $p = v_\parallel / v$

Units: [neutrons/(s·fast-ion·dE·dp)]

### Calculation Procedure

The weight function calculation in `neutron_weights` (src/fidasim.f90:15046) follows these steps:

#### 1. Phase Space Grid Setup

```fortran
! Energy grid: uniform spacing from 0 to emax_nc_wght
E_i = (i - 0.5) × E_max / N_E    for i = 1...N_E

! Pitch grid: uniform spacing from -1 to +1
p_j = (j - 0.5) × 2 / N_p - 1     for j = 1...N_p
```

Typical grids: 50-100 energy bins, 30-50 pitch bins

#### 2. Line-of-Sight Integration

For each (E, p, channel) point:

```
1. Define detector position and sightline direction
2. Track through plasma using track_cylindrical
   - Generates series of points along sightline
   - Only includes points inside plasma boundary
3. For each point along the sightline:
   - Calculate position r_n
   - Get local plasma parameters (T_i, n_D, etc.)
   - Get local magnetic field for pitch calculation
```

#### 3. Gyro-Averaging

At each spatial point, the calculation averages over 20 gyro-angles:

```
For γ = 1 to 20:
    - Calculate fast-ion position with gyro-correction
    - Determine fast-ion velocity vector from (E, p)
    - Calculate effective energy including plasma rotation
    - Compute DD reaction rate
    - Apply anisotropy correction
    - Accumulate weight contribution
```

Gyro-averaging is essential because:
- Fast-ions gyrate around magnetic field lines
- The gyro-radius can be several centimeters for energetic ions
- Emission occurs from the gyro-orbit, not a single point
- Different gyro-phases contribute differently due to velocity-dependent rates

#### 4. Weight Accumulation

The weight contribution from each point is:

$$
W(E,p,\text{chan}) += \frac{R_{\text{DD}}(E) \times \kappa(\theta) \times d\Omega \times \Delta s}{N_\gamma \times \Delta E \times \Delta p}
$$

where:
- $R_{\text{DD}}$ is the DD reaction rate [1/s]
- $\kappa$ is the anisotropy correction factor
- $d\Omega$ is the solid angle subtended by the detector
- $\Delta s$ is the path length element (stored as `tracks(i)%time` in normalized units)
- $N_\gamma = 20$ is the number of gyro-angles
- $\Delta E$, $\Delta p$ are the phase-space bin sizes

The divisions by $\Delta E$ and $\Delta p$ ensure proper normalization so that the weight function represents a density in phase space.

#### 5. Parallel Computation

The triple loop over channels, pitch, and energy is parallelized using OpenMP:

```fortran
!$OMP PARALLEL DO schedule(guided) collapse(3)
do ichan = 1, nchan
    do ip = 1, np_nc
        do ie = 1, ne_nc
            ! Weight calculation
        enddo
    enddo
enddo
!$OMP END PARALLEL DO
```

This provides excellent scaling on multi-core systems since the weight calculations for different phase-space points are independent.

### Flux Calculation

In addition to the weight function, the code calculates the actual neutron flux when a fast-ion distribution is available:

$$
\Phi_n(E, \text{chan}) = \sum_{\text{plasma}} \sum_p W(E,p,\text{chan}) \times F(E,p) \, \Delta p
$$

This convolves the weight function with the fast-ion distribution function to predict the actual neutron energy spectrum detected by each channel.

## Spatial Emissivity Calculation

When `calc_nc_wght >= 2`, FIDASIM also calculates the channel-resolved neutron emissivity on the R-Z grid:

$$
\varepsilon(R, Z, \text{chan}) = \int \int W_{\text{local}}(R,Z,E,p,\text{chan}) \times F(R,Z,E,p) \, dE \, dp
$$

This provides a spatial map showing where in the plasma each channel is sensitive.

**Physical Meaning**: The emissivity represents the neutron production rate per unit volume at each spatial location that contributes to the detector signal, accounting for:
- Solid angle from that location
- Local plasma parameters (density, temperature)
- Local fast-ion distribution
- Anisotropy of neutron emission

**Uses**:
- Visualizing the spatial sensitivity of each channel
- Understanding which plasma regions contribute most to the signal
- Validating geometric configurations
- Diagnosing unexpected signals

The emissivity calculation differs from the weight function calculation:
- Weight functions integrate along sightlines
- Emissivity is calculated on a fixed R-Z grid
- Both use the same physical models (rates, anisotropy, solid angle)

## Usage and Configuration

### Input Parameters

The neutron collimator diagnostic is controlled by parameters in the `inputs` structure:

```fortran
! Enable neutron calculations
calc_neutron = 2         ! 0=off, 1=on, 2=on with extra output

! Enable neutron spectroscopy
calc_neut_spec = 2       ! 0=off, 1=on, 2=on with full spectra

! Enable NC weight function calculation
calc_nc_wght = 2         ! 0=off, 1=weights only, 2=weights + emissivity

! Phase space grid for weight functions
ne_nc = 100              ! Number of energy bins
np_nc = 50               ! Number of pitch bins
emax_nc_wght = 120.0     ! Maximum energy [keV]
```

### Requirements

For the NC diagnostic to function:

1. **Plasma must contain thermal deuterium**: The code checks for deuterium in the `thermal_mass` array
2. **Beam species must be deuterium**: Fast-ion species must have `beam_mass = H2_amu`
3. **Geometry must be provided**: An `/nc` group must exist in the geometry HDF5 file
4. **Distribution function available**: For flux/emissivity calculations, `dist_type = 1` (distribution function F)

### Geometry File Structure

The neutron collimator geometry is stored in the HDF5 geometry file under `/nc/`:

```
/nc/
  nchan          - Number of channels [integer]
  system         - System identifier [string]
  radius         - Channel radius values [nchan] (cm)
  a_shape        - Aperture shape [nchan]: 1=rectangular, 2=circular
  a_cent         - Aperture center positions [3, nchan] (cm)
  a_redge        - Aperture radial edge vectors [3, nchan] (cm)
  a_tedge        - Aperture toroidal edge vectors [3, nchan] (cm)
  d_shape        - Detector shape [nchan]: 1=rectangular, 2=circular
  d_cent         - Detector center positions [3, nchan] (cm)
  d_redge        - Detector radial edge vectors [3, nchan] (cm)
  d_tedge        - Detector toroidal edge vectors [3, nchan] (cm)
```

All positions and vectors are specified in the UVW coordinate system defined by the beam grid.

## Output Files

### Weight Function File

When `calc_nc_wght > 0`, the code produces `{runid}_nc_weights.h5` containing:

```
/energy          - Energy grid [ne_nc] (keV)
/pitch           - Pitch grid [np_nc] (dimensionless, -1 to +1)
/weight          - Weight function [ne_nc, np_nc, nchan] (neutrons/(s·ion·dE·dp))
/flux            - Neutron energy flux [ne_nc, nchan] (neutrons/(s·dE))
/radius          - R grid for emissivity [nr] (cm)
/z               - Z grid for emissivity [nz] (cm)
/emissivity      - (optional) Spatial emissivity [nr, nz, nchan] (neutrons/(s·cm³))
/nchan           - Number of channels
```

### Interpreting Weight Functions

**Shape Characteristics**:
- **Energy dependence**: Weight typically peaks at moderate energies (30-80 keV) where the DD cross-section is significant but fast-ions are still relatively abundant
- **Pitch dependence**: Shape depends on geometry and magnetic field topology; channels viewing along field lines may show pitch-dependent structure
- **Channel dependence**: Different channels sample different plasma regions with different plasma parameters and geometric factors

**Quality Checks**:
1. Weights should be smooth (no spikes or noise)
2. Weights should be zero outside physically accessible regions
3. Sum over pitch should show reasonable energy dependence
4. Flux predictions should match direct neutron calculations when available

## Physical Insights and Applications

### Velocity-Space Tomography

Weight functions enable velocity-space tomography - reconstructing the 2D fast-ion distribution F(E, p) from multi-channel measurements:

$$
\Phi_{\text{measured},i} = \sum_{E,p} W_i(E,p) F(E,p) \Delta E \Delta p + \text{noise}
$$

This is an inverse problem that can be solved with regularization techniques. Multiple channels with different geometries provide complementary views of velocity space.

### Diagnostic Design

Weight functions are invaluable for designing and optimizing neutron collimator systems:

- **Sensitivity maps**: Identify regions of velocity space each channel probes
- **Overlap analysis**: Ensure channels provide complementary information
- **Resolution studies**: Understand trade-offs between spatial and phase-space resolution
- **Background estimation**: Separate thermal-thermal from beam-thermal contributions

### Benchmarking Fast-Ion Codes

Comparing predicted weight functions and neutron signals with measurements provides stringent tests of:
- Fast-ion distribution calculations (NUBEAM, ASCOT, etc.)
- Classical vs. anomalous transport models
- Wave-particle interaction models (ICRF, NBI)

### Multi-Diagnostic Integration

Neutron collimator measurements complement other fast-ion diagnostics:
- **FIDA**: High resolution in velocity space but spatially limited
- **NPA**: Direct velocity-space measurement but limited sightlines
- **Neutron Cameras**: Better spatial resolution but less velocity-space detail
- **NC**: Bridge between spatial and velocity-space diagnostics

Combined analysis using multiple diagnostics provides the most complete picture of the fast-ion distribution.

## Computational Considerations

### Performance

Weight function calculations are computationally intensive because:
- Triple loop over (energy, pitch, channels)
- Line-of-sight integration for each point
- Gyro-averaging (20 points per spatial location)
- Plasma and field interpolations at each point

Typical calculation times:
- 50×50 phase-space grid, 47 channels: ~5-20 minutes on modern multi-core CPU
- Scales approximately linearly with number of channels
- OpenMP parallelization provides near-linear speedup up to ~20 cores

### Memory Usage

Memory requirements scale with:
- Weight array: `8 bytes × ne_nc × np_nc × nchan`
- Example: 100×50×47 ≈ 1.9 MB (negligible)
- Emissivity array: `8 bytes × nr × nz × nchan`
- Example: 100×100×47 ≈ 3.8 MB (negligible)

Memory is rarely a limiting factor for NC calculations.

### Accuracy Considerations

Several factors affect numerical accuracy:

1. **Energy grid resolution**: 50-100 bins typically sufficient; very peaked distributions may need finer grids
2. **Pitch grid resolution**: 30-50 bins usually adequate; trapped-passing boundary regions may need more
3. **Gyro-angle sampling**: 20 points provides <1% error for most cases
4. **Spatial discretization**: Determined by beam grid resolution; typically 1-2 cm
5. **Anisotropy interpolation**: Accurate to ~5% based on experimental data uncertainties

## Limitations and Approximations

### Current Implementation

1. **DD reactions only**: Only D+D→n+³He reactions are modeled; DT reactions not currently supported
2. **Single fast-ion species**: Assumes one energetic deuterium population
3. **No neutron scattering**: Treats neutrons as massless particles on straight trajectories (valid for MeV neutrons in plasma)
4. **Non-relativistic kinematics**: Uses non-relativistic formulas; valid for beam energies <500 keV
5. **No detector energy response**: Weight functions calculated at birth energy; does not include detector resolution or efficiency functions

### Physical Assumptions

1. **Born approximation**: Assumes neutron production point is same as fast-ion/thermal interaction point
2. **Thin plasma**: Neglects attenuation of neutrons in plasma (negligible for fusion plasmas)
3. **Steady-state**: Assumes plasma and fast-ion distribution are static during diagnostic integration time
4. **Localized emission**: Gyro-averaging assumes emission occurs near guiding center (good for ρ << L_plasma)

These approximations are generally excellent for fusion plasmas and introduce errors well below experimental uncertainties.

## References and Further Reading

1. **DD Cross Sections**:
   - Bosch & Hale, "Improved formulas for fusion cross-sections and thermal reactivities," Nucl. Fusion 32, 611 (1992)

2. **DD Anisotropy**:
   - Brown & Jarmie, "Differential cross sections at low energies for ²H(d,p)³H and ²H(d,n)³He," Phys. Rev. C 41, 1391 (1990)
   - NIM A236, 380 (1985)

3. **Neutron Diagnostics**:
   - Järvinen et al., "Neutron emission spectroscopy measurements and modelling on ASDEX Upgrade," Rev. Sci. Instrum. 90, 103501 (2019)
   - Eriksson et al., "Calculating fusion neutron energy spectra from arbitrary reactant distributions," Comp. Phys. Comm. 199, 40 (2016)

4. **Fast-Ion Physics**:
   - Heidbrink & Sadler, "The behaviour of fast ions in tokamak experiments," Nucl. Fusion 34, 535 (1994)
   - FIDASIM documentation: [Weight Functions](./07_weights.html)

5. **Velocity-Space Tomography**:
   - Salewski et al., "On velocity-space sensitivity of fast-ion D-alpha spectroscopy," Plasma Phys. Control. Fusion 56, 105005 (2014)
   - Papers applying tomography to neutron measurements

## Example Workflow

A typical workflow for using the NC diagnostic:

```python
# 1. Set up geometry (Python/IDL preprocessing)
import h5py

# Define detector and aperture positions
# ... geometry setup code ...

with h5py.File('geometry.h5', 'a') as f:
    nc = f.create_group('nc')
    nc['nchan'] = n_channels
    nc['a_cent'] = aperture_centers
    nc['d_cent'] = detector_centers
    # ... additional geometry arrays ...

# 2. Configure FIDASIM input file
"""
&fidasim_inputs
    ...
    calc_neutron = 2
    calc_nc_wght = 2
    ne_nc = 100
    np_nc = 50
    emax_nc_wght = 120.0
    ...
/
"""

# 3. Run FIDASIM
# $ mpirun -np 8 ./fidasim input.dat

# 4. Analyze outputs
import h5py
import numpy as np
import matplotlib.pyplot as plt

# Read weight functions
with h5py.File('runid_nc_weights.h5', 'r') as f:
    energy = f['energy'][:]
    pitch = f['pitch'][:]
    weight = f['weight'][:]  # (ne, np, nchan)
    flux = f['flux'][:]      # (ne, nchan)

# Plot weight function for channel 1
plt.figure()
plt.contourf(pitch, energy, weight[:,:,0])
plt.xlabel('Pitch')
plt.ylabel('Energy [keV]')
plt.title('NC Weight Function - Channel 1')
plt.colorbar(label='Weight [n/(s·ion·dE·dp)]')
plt.show()

# Compare predicted vs measured flux
flux_measured = load_experimental_data()
plt.plot(energy, flux[:,0], label='FIDASIM')
plt.plot(energy_exp, flux_measured, 'o', label='Experiment')
plt.xlabel('Energy [keV]')
plt.ylabel('Flux [n/(s·dE)]')
plt.legend()
plt.show()
```

## Summary

The neutron collimation diagnostic in FIDASIM provides comprehensive modeling of collimated neutron detection for fast-ion diagnosis. Key features include:

- **Complete physics**: DD reaction rates, proper kinematics, anisotropy corrections
- **Weight functions**: Phase-space sensitivity W(E, p, channel)
- **Flexible geometry**: Supports multiple channels with arbitrary detector/aperture configurations
- **Spatial resolution**: Optional emissivity calculations on R-Z grid
- **Optimized performance**: OpenMP parallelization for efficient calculations
- **Integration**: Works seamlessly with FIDASIM's fast-ion distributions

The implementation in FIDASIM enables forward modeling for experimental validation, inverse techniques for distribution reconstruction, and diagnostic design optimization.

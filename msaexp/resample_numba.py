import numpy as np
from numba import jit
from math import erf

__all__ = [
    "resample_template_numba",
    "sample_gaussian_line_numba",
    "pixel_integrated_gaussian_numba",
    "compute_igm",
]


@jit(nopython=True, fastmath=True, error_model="numpy")
def resample_template_numba(
    spec_wobs,
    spec_R_fwhm,
    templ_wobs,
    templ_flux,
    velocity_sigma=100,
    nsig=5,
    fill_value=0.0,
):
    """
    Resample a high resolution template/model on the wavelength grid of a
    spectrum with (potentially) wavelength dependent dispersion

    Parameters
    ----------
    spec_wobs : array-like
        Spectrum wavelengths

    spec_R_fwhm : array-like
        Spectral resolution `wave/d(wave)`, FWHM

    templ_wobs : array-like
        Template wavelengths, observed frame.  Same units as `spec_wobs`.
        **NB:** both `spec_wobs` and `templ_wobs` assumed to be sorted!

    templ_flux : array-like
        Template flux densities sampled at `templ_wobs`

    velocity_sigma : float
        Kinematic velocity width, km/s

    nsig : float
        Number of sigmas of the Gaussian convolution kernel to sample

    fill_value : float
        Value to fill in the resampled array where no template data is available

    Returns
    -------
    resamp : array-like
        Template resampled at the `spec_wobs` wavelengths, convolved with a
        Gaussian kernel with sigma width

        >>> Rw = 1./np.sqrt((velocity_sigma/3.e5)**2 + 1./(spec_R_fwhm*2.35)**2)
        >>> dw = spec_wobs / Rw

    """
    dw = (
        np.sqrt(
            (velocity_sigma / 3.0e5) ** 2 + (1.0 / 2.35 / spec_R_fwhm) ** 2
        )
        * spec_wobs
    )

    # Rw = 1./np.sqrt((velocity_sigma/3.e5)**2 + 1./(spec_R_fwhm*2.35)**2)
    # dw = spec_wobs / Rw

    ilo = 0
    ihi = 1

    N = len(spec_wobs)
    resamp = np.zeros_like(spec_wobs) * fill_value

    Nt = len(templ_wobs)

    for i in range(N):
        # sl = slice(ilo[i], ihi[i])
        while (templ_wobs[ilo] < spec_wobs[i] - nsig * dw[i]) & (ilo < Nt - 1):
            ilo += 1

        if ilo == 0:
            continue

        ilo -= 1

        while (templ_wobs[ihi] < spec_wobs[i] + nsig * dw[i]) & (ihi < Nt):
            ihi += 1

        if ilo >= ihi:
            resamp[i] = templ_flux[ihi]
            continue
        elif ilo == Nt - 1:
            break

        sl = slice(ilo, ihi)
        lsl = templ_wobs[sl]
        g = np.exp(-((lsl - spec_wobs[i]) ** 2) / 2 / dw[i] ** 2) / np.sqrt(
            2 * np.pi * dw[i] ** 2
        )
        # g *= 1./np.sqrt(2*np.pi*dw[i]**2)
        resamp[i] = np.trapz(templ_flux[sl] * g, lsl)

    return resamp


@jit(nopython=True, fastmath=True, error_model="numpy")
def sample_gaussian_line_numba(
    spec_wobs,
    spec_R_fwhm,
    line_um,
    line_flux=1.0,
    velocity_sigma=100,
):
    """
    Sample a Gaussian emission line on the spectrum wavelength grid accounting
    for pixel integration

    Parameters
    ----------
    spec_wobs : array-like
        Spectrum wavelengths

    spec_R_fwhm : array-like
        Spectral resolution `wave/d(wave)`, FWHM

    line_um : float
        Emission line central wavelength, in microns

    line_flux : float
        Normalization of the line

    velocity_sigma : float
        Kinematic velocity width, km/s

    Returns
    -------
    resamp : array-like
        Emission line "template" resampled at the `spec_wobs` wavelengths

    """

    Rw = np.interp(line_um, spec_wobs, spec_R_fwhm)
    dw = (
        np.sqrt((velocity_sigma / 3.0e5) ** 2 + (1.0 / 2.35 / Rw) ** 2)
        * line_um
    )

    resamp = pixel_integrated_gaussian_numba(
        spec_wobs, line_um, dw, normalization=line_flux
    )

    return resamp


@jit(nopython=True, fastmath=True, error_model="numpy")
def pixel_integrated_gaussian_numba(x, mu, sigma, dx=None, normalization=1.0):
    """
    Low level function for a pixel-integrated gaussian

    Parameters
    ----------
    x : array-like
        Sample centers

    mu : float, array-like
        Gaussian center

    sigma : float, array-like
        Gaussian width

    dx : float, array-like
        Difference to override ``x[i+1] - x[i]`` if not provided as zero

    normalization : float
        Scaling

    Returns
    -------
    samp : array-like
        Pixel-integrated Gaussian

    """
    N = len(x)
    samp = np.zeros_like(x)

    s2dw = np.sqrt(2) * sigma * np.ones_like(x)

    mux = mu * np.ones_like(x)

    if dx is None:
        # Like np.gradient
        # https://github.com/numba/numba/issues/6302
        xdx = np.ones_like(x)
        xdx[1:-1] = (x[2:] - x[:-2]) / 2.0
        xdx[0] = x[1] - x[0]
        xdx[-1] = x[-1] - x[-2]
    else:
        xdx = dx * np.ones_like(x)

    i = 0
    x0 = x[i] - mux[i]

    left = erf((x0 - xdx[i] / 2) / s2dw[i])
    right = erf((x0 + xdx[i] / 2) / s2dw[i])
    samp[i] = (right - left) / 2 / xdx[i] * normalization

    for i in range(1, N):
        x0 = x[i] - mux[i]
        left = erf((x0 - xdx[i] / 2) / s2dw[i])
        right = erf((x0 + xdx[i] / 2) / s2dw[i])
        samp[i] = (right - left) / 2 / xdx[i] * normalization

    return samp


@jit(nopython=True, fastmath=True, error_model="numpy")
def compute_igm(z, wobs, scale_tau=1.0):
    """
    Calculate
    `Inoue+ (2014) <https://ui.adsabs.harvard.edu/abs/2014MNRAS.442.1805I>`_
    IGM transmission, reworked from `~eazy.igm.Inoue14`

    Parameters
    ----------
    z : float
        Redshift

    wobs : array-like
        Observed-frame wavelengths, Angstroms

    scale_tau : float
        Scalar multiplied to tau_igm

    Returns
    -------
    igmz : array-like
        IGM transmission factor
    """

    _LAF = np.array(
        [
            [2, 1215.670, 1.68976e-02, 2.35379e-03, 1.02611e-04],
            [3, 1025.720, 4.69229e-03, 6.53625e-04, 2.84940e-05],
            [4, 972.537, 2.23898e-03, 3.11884e-04, 1.35962e-05],
            [5, 949.743, 1.31901e-03, 1.83735e-04, 8.00974e-06],
            [6, 937.803, 8.70656e-04, 1.21280e-04, 5.28707e-06],
            [7, 930.748, 6.17843e-04, 8.60640e-05, 3.75186e-06],
            [8, 926.226, 4.60924e-04, 6.42055e-05, 2.79897e-06],
            [9, 923.150, 3.56887e-04, 4.97135e-05, 2.16720e-06],
            [10, 920.963, 2.84278e-04, 3.95992e-05, 1.72628e-06],
            [11, 919.352, 2.31771e-04, 3.22851e-05, 1.40743e-06],
            [12, 918.129, 1.92348e-04, 2.67936e-05, 1.16804e-06],
            [13, 917.181, 1.62155e-04, 2.25878e-05, 9.84689e-07],
            [14, 916.429, 1.38498e-04, 1.92925e-05, 8.41033e-07],
            [15, 915.824, 1.19611e-04, 1.66615e-05, 7.26340e-07],
            [16, 915.329, 1.04314e-04, 1.45306e-05, 6.33446e-07],
            [17, 914.919, 9.17397e-05, 1.27791e-05, 5.57091e-07],
            [18, 914.576, 8.12784e-05, 1.13219e-05, 4.93564e-07],
            [19, 914.286, 7.25069e-05, 1.01000e-05, 4.40299e-07],
            [20, 914.039, 6.50549e-05, 9.06198e-06, 3.95047e-07],
            [21, 913.826, 5.86816e-05, 8.17421e-06, 3.56345e-07],
            [22, 913.641, 5.31918e-05, 7.40949e-06, 3.23008e-07],
            [23, 913.480, 4.84261e-05, 6.74563e-06, 2.94068e-07],
            [24, 913.339, 4.42740e-05, 6.16726e-06, 2.68854e-07],
            [25, 913.215, 4.06311e-05, 5.65981e-06, 2.46733e-07],
            [26, 913.104, 3.73821e-05, 5.20723e-06, 2.27003e-07],
            [27, 913.006, 3.45377e-05, 4.81102e-06, 2.09731e-07],
            [28, 912.918, 3.19891e-05, 4.45601e-06, 1.94255e-07],
            [29, 912.839, 2.97110e-05, 4.13867e-06, 1.80421e-07],
            [30, 912.768, 2.76635e-05, 3.85346e-06, 1.67987e-07],
            [31, 912.703, 2.58178e-05, 3.59636e-06, 1.56779e-07],
            [32, 912.645, 2.41479e-05, 3.36374e-06, 1.46638e-07],
            [33, 912.592, 2.26347e-05, 3.15296e-06, 1.37450e-07],
            [34, 912.543, 2.12567e-05, 2.96100e-06, 1.29081e-07],
            [35, 912.499, 1.99967e-05, 2.78549e-06, 1.21430e-07],
            [36, 912.458, 1.88476e-05, 2.62543e-06, 1.14452e-07],
            [37, 912.420, 1.77928e-05, 2.47850e-06, 1.08047e-07],
            [38, 912.385, 1.68222e-05, 2.34330e-06, 1.02153e-07],
            [39, 912.353, 1.59286e-05, 2.21882e-06, 9.67268e-08],
            [40, 912.324, 1.50996e-05, 2.10334e-06, 9.16925e-08],
        ]
    ).T

    ALAM = _LAF[1]
    ALAF1 = _LAF[2]
    ALAF2 = _LAF[3]
    ALAF3 = _LAF[4]

    _DLA = np.array(
        [
            [2, 1215.670, 1.61698e-04, 5.38995e-05],
            [3, 1025.720, 1.54539e-04, 5.15129e-05],
            [4, 972.537, 1.49767e-04, 4.99222e-05],
            [5, 949.743, 1.46031e-04, 4.86769e-05],
            [6, 937.803, 1.42893e-04, 4.76312e-05],
            [7, 930.748, 1.40159e-04, 4.67196e-05],
            [8, 926.226, 1.37714e-04, 4.59048e-05],
            [9, 923.150, 1.35495e-04, 4.51650e-05],
            [10, 920.963, 1.33452e-04, 4.44841e-05],
            [11, 919.352, 1.31561e-04, 4.38536e-05],
            [12, 918.129, 1.29785e-04, 4.32617e-05],
            [13, 917.181, 1.28117e-04, 4.27056e-05],
            [14, 916.429, 1.26540e-04, 4.21799e-05],
            [15, 915.824, 1.25041e-04, 4.16804e-05],
            [16, 915.329, 1.23614e-04, 4.12046e-05],
            [17, 914.919, 1.22248e-04, 4.07494e-05],
            [18, 914.576, 1.20938e-04, 4.03127e-05],
            [19, 914.286, 1.19681e-04, 3.98938e-05],
            [20, 914.039, 1.18469e-04, 3.94896e-05],
            [21, 913.826, 1.17298e-04, 3.90995e-05],
            [22, 913.641, 1.16167e-04, 3.87225e-05],
            [23, 913.480, 1.15071e-04, 3.83572e-05],
            [24, 913.339, 1.14011e-04, 3.80037e-05],
            [25, 913.215, 1.12983e-04, 3.76609e-05],
            [26, 913.104, 1.11972e-04, 3.73241e-05],
            [27, 913.006, 1.11002e-04, 3.70005e-05],
            [28, 912.918, 1.10051e-04, 3.66836e-05],
            [29, 912.839, 1.09125e-04, 3.63749e-05],
            [30, 912.768, 1.08220e-04, 3.60734e-05],
            [31, 912.703, 1.07337e-04, 3.57789e-05],
            [32, 912.645, 1.06473e-04, 3.54909e-05],
            [33, 912.592, 1.05629e-04, 3.52096e-05],
            [34, 912.543, 1.04802e-04, 3.49340e-05],
            [35, 912.499, 1.03991e-04, 3.46636e-05],
            [36, 912.458, 1.03198e-04, 3.43994e-05],
            [37, 912.420, 1.02420e-04, 3.41402e-05],
            [38, 912.385, 1.01657e-04, 3.38856e-05],
            [39, 912.353, 1.00908e-04, 3.36359e-05],
            [40, 912.324, 1.00168e-04, 3.33895e-05],
        ]
    ).T

    ADLA1 = _DLA[2]
    ADLA2 = _DLA[3]

    def _pow(a, b):
        return a**b

    ####
    # Lyman series, Lyman-alpha forest
    ####
    z1LAF = 1.2
    z2LAF = 4.7

    ###
    # Lyman Series, DLA
    ###
    z1DLA = 2.0

    ###
    # Lyman continuum, DLA
    ###
    lamL = 911.8

    tau = np.zeros_like(wobs)
    zS = z

    # Explicit iteration should be fast in JIT
    for i, wi in enumerate(wobs):
        if wi > 1300.0 * (1 + zS):
            continue

        # Iterate over Lyman series
        for j, lsj in enumerate(ALAM):
            # LS LAF
            if wi < lsj * (1 + zS):
                if wi < lsj * (1 + z1LAF):
                    # x1
                    tau[i] += ALAF1[j] * (wi / lsj) ** 1.2
                elif (wi >= lsj * (1 + z1LAF)) & (wi < lsj * (1 + z2LAF)):
                    tau[i] += ALAF2[j] * (wi / lsj) ** 3.7
                else:
                    tau[i] += ALAF3[j] * (wi / lsj) ** 5.5

            # LS DLA
            if wi < lsj * (1 + zS):
                if wi < lsj * (1.0 + z1DLA):
                    tau[i] += ADLA1[j] * (wi / lsj) ** 2
                else:
                    tau[i] += ADLA2[j] * (wi / lsj) ** 3

        # Lyman Continuum
        if wi < lamL * (1 + zS):
            # LC DLA
            if zS < z1DLA:
                tau[i] += (
                    0.2113 * _pow(1 + zS, 2)
                    - 0.07661 * _pow(1 + zS, 2.3) * _pow(wi / lamL, (-3e-1))
                    - 0.1347 * _pow(wi / lamL, 2)
                )
            else:
                x1 = wi >= lamL * (1 + z1DLA)
                if wi >= lamL * (1 + z1DLA):
                    tau[i] += (
                        0.04696 * _pow(1 + zS, 3)
                        - 0.01779
                        * _pow(1 + zS, 3.3)
                        * _pow(wi / lamL, (-3e-1))
                        - 0.02916 * _pow(wi / lamL, 3)
                    )
                else:
                    tau[i] += (
                        0.6340
                        + 0.04696 * _pow(1 + zS, 3)
                        - 0.01779
                        * _pow(1 + zS, 3.3)
                        * _pow(wi / lamL, (-3e-1))
                        - 0.1347 * _pow(wi / lamL, 2)
                        - 0.2905 * _pow(wi / lamL, (-3e-1))
                    )

            # LC LAF
            if zS < z1LAF:
                tau[i] += 0.3248 * (
                    _pow(wi / lamL, 1.2)
                    - _pow(1 + zS, -9e-1) * _pow(wi / lamL, 2.1)
                )
            elif zS < z2LAF:
                if wi >= lamL * (1 + z1LAF):
                    tau[i] += 2.545e-2 * (
                        _pow(1 + zS, 1.6) * _pow(wi / lamL, 2.1)
                        - _pow(wi / lamL, 3.7)
                    )
                else:
                    tau[i] += (
                        2.545e-2 * _pow(1 + zS, 1.6) * _pow(wi / lamL, 2.1)
                        + 0.3248 * _pow(wi / lamL, 1.2)
                        - 0.2496 * _pow(wi / lamL, 2.1)
                    )
            else:
                if wi > lamL * (1.0 + z2LAF):
                    tau[i] += 5.221e-4 * (
                        _pow(1 + zS, 3.4) * _pow(wi / lamL, 2.1)
                        - _pow(wi / lamL, 5.5)
                    )
                elif (wi >= lamL * (1 + z1LAF)) & (wi < lamL * (1 + z2LAF)):
                    tau[i] += (
                        5.221e-4 * _pow(1 + zS, 3.4) * _pow(wi / lamL, 2.1)
                        + 0.2182 * _pow(wi / lamL, 2.1)
                        - 2.545e-2 * _pow(wi / lamL, 3.7)
                    )
                elif wi < lamL * (1 + z1LAF):
                    tau[i] += (
                        5.221e-4 * _pow(1 + zS, 3.4) * _pow(wi / lamL, 2.1)
                        + 0.3248 * _pow(wi / lamL, 1.2)
                        - 3.140e-2 * _pow(wi / lamL, 2.1)
                    )

    igmz = np.exp(-scale_tau * tau)

    return igmz

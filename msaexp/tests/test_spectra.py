
import os

import numpy as np
import matplotlib.pyplot as plt
plt.ioff()

from .. import utils, spectrum, pipeline

pipe = None
TARGETS = ['1345_933']
eazy_templates = None

def data_path():
    return os.path.join(os.path.dirname(__file__), 'data')
    
def test_init():
    """
    Initialize pipeline object with previously-extracted slitlets
    """
    import glob
    global pipe
    
    os.chdir(data_path())
    
    
    mode = 'jw01345062001_03101_00001_nrs2'
    
    files = [f'jw01345062001_03101_0000{i}_nrs2_rate.fits'
             for i in [1,2,3]]
    
    pipe = pipeline.NirspecPipeline(mode=mode, files=files)
    
    pipe.full_pipeline(run_extractions=False,
                       initialize_bkg=True,
                       targets=TARGETS,
                       load_saved='phot')


def test_extract_spectra():
    """
    Extract single spectra
    """
    fit_profile = {'min_delta':20}
    yoffset = 0.01
    
    key = TARGETS[0]
    
    _data = pipe.extract_spectrum(key, skip=[],
                              yoffset=yoffset,
                              prof_sigma=0.7,
                              trace_sign=-1, 
                              fit_profile_params=fit_profile,
                              )
    
    plt.close('all')
    
    slitlet, sep1d, opt1d, fig = _data


def test_drizzle_combine():
    """
    Drizzle combination
    """
    DRIZZLE_PARAMS = dict(output=None,
                          single=True,
                          blendheaders=True,
                          pixfrac=0.6,
                          kernel='square',
                          fillval=0,
                          wht_type='ivm',
                          good_bits=0,
                          pscale_ratio=1.0,
                          pscale=None,
                          verbose=False)
    
    key = TARGETS[0]
    
    slits = []
    slits += pipe.get_background_slits(key, step='bkg', check_background=True)

    for slit in slits:
        slit.dq = slit.dq & (1+1024)
    
    print(f'{key}  N= {len(slits)}  slits')

    hdul = utils.drizzle_2d_pipeline(slits, 
                                     drizzle_params=DRIZZLE_PARAMS,
                                     fit_prf=True,
                                     outlier_threshold=30000,
                                     prf_center=-0.0,
                                     prf_sigma=1.0,
                                     fix_sigma=True,
                                     center_limit=6.0, 
                                     standard_waves=False,
                                     # profile_slice=slice(100,150),
                                     )

    z = 4.2341
    _fig = utils.drizzled_hdu_figure(hdul,
                                     z=z,
                                     xlim=None,
                                     unit='fnu')
    ax = _fig.axes[2]
    xl = ax.get_xlim()

    ax.text(0.02, 0.82, key, ha='left', va='bottom', transform=ax.transAxes)
    
    plt.close('all')
    froot = 'ceers-prism'
    hdul.writeto(f'{froot}.{key}.v0.spec.fits', overwrite=True)


def test_load_templates():
    
    import eazy
    global eazy_templates
    
    cwd = os.getcwd()
    
    path = os.path.join(os.path.dirname(eazy.__file__), 'data/')
    
    os.chdir(path)
    
    _param = 'templates/sfhz/carnall_sfhz_13.param'
    eazy_templates = eazy.templates.read_templates_file(_param)
    
    os.chdir(cwd)


def test_fit_redshift():
    """
    Redshift fit with spline + line templates
    """
    global eazy_templates
    
    z0 = [4, 5]
    
    kws = dict(eazy_templates=None,
               scale_disp=1.0,
               nspline=33, 
               Rline=2000, 
               use_full_dispersion=False,
               vel_width=100,
               )
    
    z=4.2341
    
    fig, zfit = spectrum.plot_spectrum(f'ceers-prism.1345_933.v0.spec.fits',
                                       z=z,
                                       **kws)
    
    fig.savefig('ceers-prism.1345_933.v0.spec.spl.png')
    
    assert('z' in zfit)
    
    assert(np.allclose(zfit['z'], z))
    
    assert('coeffs' in zfit)
    assert(np.allclose(zfit['coeffs']['line OIII'],
          [2380.506645630245, 35.5975856294446]))
    
    
    if eazy_templates is not None:
        kws['eazy_templates'] = eazy_templates
        kws['use_full_dispersion'] = False
        fig, zfit = spectrum.fit_redshift(f'ceers-prism.1345_933.v0.spec.fits',
                              z0=[4,5],
                              is_prism=True,
                              **kws)
        
        plt.close('all')
        assert('z' in zfit)
    
        assert(np.allclose(zfit['z'], z, rtol=0.01))
    
        assert('coeffs' in zfit)
        assert(np.allclose(zfit['coeffs']['4590.fits'],
                           [115.4471, 3.2553],
                           rtol=0.01))
        
        # With dispersion
        kws['use_full_dispersion'] = True
        fig, zfit = spectrum.fit_redshift(f'ceers-prism.1345_933.v0.spec.fits',
                              z0=[4,5],
                              is_prism=True,
                              **kws)
        
        plt.close('all')
        assert('z' in zfit)
    
        assert(np.allclose(zfit['z'], z, rtol=0.01))
    
        assert('coeffs' in zfit)
        assert(np.allclose(zfit['coeffs']['4590.fits'],
                           [75.95547, 3.7042],
                           rtol=0.01))

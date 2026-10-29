"""
Varsha — Data Fetchers Package

Each module downloads one public data source:
- chirps.py      : CHIRPS 2.0 daily rainfall (open)
- enso_oni.py    : NOAA CPC ONI index (open)
- iod_dmi.py     : IOD Dipole Mode Index (open)
- mjo_bsiso.py   : MJO RMM + BSISO indices (open)
- imd_gridded.py : IMD 0.25° gridded rainfall (needs institutional access)
- era5.py        : ERA5 reanalysis (needs CDS API key)
- cfsv2.py       : CFSv2 forecasts (open via NOMADS)
- smap_sm.py     : SMAP soil moisture (needs Earthdata login)
- srtm_dem.py    : SRTM DEM (open)
- lgd_boundaries.py : LGD block/panchayat boundaries (open)
"""

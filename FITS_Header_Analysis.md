# FITS Header Analysis Report

- **Scan Directory**: `/Users/yvinu/Temp_stacking`
- **Timestamp**: 2026-09-13 13:28:40
- **Total Files Found**: 11368 (Symlinks: 15)
- **Successfully Processed**: 11280
- **Failed Files**: 88

## 1. Most Common Set of Fields / Cards

The table below shows header key-sets appearing in >= 1.0% of scanned files:

| Rank | Files | Coverage | Field Count | Common Header Fields |
|---|---|---|---|---|
| 1 | 6935 | 61.48% | 40 | `APTDIA, BAYERPAT, BSCALE, BZERO, CAMERA, CAMNAME, CCD-TEMP, COMMENT, DATE, DATE-OBS...` |
| 2 | 1665 | 14.76% | 36 | `APERTURE, BAYERPAT, BSCALE, BZERO, CCD-TEMP, CCDXBIN, CCDYBIN, COMMENT, CREATOR, DATE-EXP...` |
| 3 | 1036 | 9.18% | 28 | `BAYERPAT, CALMAX, CALMIN, CAMERA, DATE-OBS, DEBAYERED, DEC, DET-TEMP, EQMODE, EXPTIME...` |
| 4 | 947 | 8.4% | 26 | `BAYERPAT, CALMAX, CALMIN, CAMERA, DATE-OBS, DEC, DET-TEMP, EQMODE, EXPTIME, FILTER...` |
| 5 | 412 | 3.65% | 24 | `BAYERPAT, BSCALE, BZERO, CAMERA, DATE-OBS, DEC, DET-TEMP, EQMODE, EXPTIME, FILTER...` |


## 2. Unique Combinations of FITS Fields

Discovered **75 total distinct field signatures**.
 *(Excluded 70 rare signatures [< 1.0%], representing 285 files / 2.53% of collection)*:

### Signature #1 (6935 files, 61.48%)
- **Field Count**: 40
- **Sample Files**: `C 20(1)_30s60_Duo-Band_20260906-233846154_42C.fits, C 20(1)_30s60_Duo-Band_20260906-234730089_42C.fits, C 20(1)_30s60_Duo-Band_20260906-233946104_42C.fits`
- **Complete Key Set**: `APTDIA, BAYERPAT, BSCALE, BZERO, CAMERA, CAMNAME, CCD-TEMP, COMMENT, DATE, DATE-OBS, DEC, DET-TEMP, EQMODE, EXPTIME, FILTER, FIRMWARE, FOCALLEN, FOCTEMP, FRAME, GAIN, HISTORY, IMAGETYP, INSTRUME, LIVETIME, MACADDR, OBJECT, OFFSET, ORIGIN, PROGRAM, RA, RESTACK, ROWORDER, SCALE, TELESCOP, XBAYROFF, XBINNING, XPIXSZ, YBAYROFF, YBINNING, YPIXSZ`

### Signature #2 (1665 files, 14.76%)
- **Field Count**: 36
- **Sample Files**: `Light_mosaic_M 20_10.0s_LP_20260806-222925.fit, Light_mosaic_M 20_10.0s_LP_20260806-231959.fit, Light_M 20_10.0s_LP_20260806-011103.fit`
- **Extra Fields vs Primary**: `APERTURE, CCDXBIN, CCDYBIN, CREATOR, DATE-EXP, EXPOSURE, FOCUSPOS, PRODUCER, SITELAT, SITELONG, TOTALEXP, WIDECAM, XORGSUBF, YORGSUBF`
- **Missing Fields vs Primary**: `APTDIA, CAMERA, CAMNAME, DATE, DET-TEMP, FIRMWARE, FOCTEMP, FRAME, HISTORY, LIVETIME, MACADDR, OFFSET, ORIGIN, RESTACK, ROWORDER, SCALE, XBAYROFF, YBAYROFF`
- **Complete Key Set**: `APERTURE, BAYERPAT, BSCALE, BZERO, CCD-TEMP, CCDXBIN, CCDYBIN, COMMENT, CREATOR, DATE-EXP, DATE-OBS, DEC, EQMODE, EXPOSURE, EXPTIME, FILTER, FOCALLEN, FOCUSPOS, GAIN, IMAGETYP, INSTRUME, OBJECT, PRODUCER, PROGRAM, RA, SITELAT, SITELONG, TELESCOP, TOTALEXP, WIDECAM, XBINNING, XORGSUBF, XPIXSZ, YBINNING, YORGSUBF, YPIXSZ`

### Signature #3 (1036 files, 9.18%)
- **Field Count**: 28
- **Sample Files**: `1daebb_cb625c_IC 1396_15s60_Duo-Band_20260901-011652764_36C_c_n_r.fit, 1daebb_cb625c_IC 1396_15s60_Duo-Band_20260901-004939163_37C_c_n_r.fit, 1daebb_cb625c_IC 1396_15s60_Duo-Band_20260901-005853681_37C_c_n_r.fit`
- **Extra Fields vs Primary**: `CALMAX, CALMIN, DEBAYERED, NAXIS3, SATMASK`
- **Missing Fields vs Primary**: `APTDIA, BSCALE, BZERO, CAMNAME, CCD-TEMP, COMMENT, DATE, FOCTEMP, FRAME, IMAGETYP, LIVETIME, OFFSET, PROGRAM, ROWORDER, SCALE, XBAYROFF, YBAYROFF`
- **Complete Key Set**: `BAYERPAT, CALMAX, CALMIN, CAMERA, DATE-OBS, DEBAYERED, DEC, DET-TEMP, EQMODE, EXPTIME, FILTER, FIRMWARE, FOCALLEN, GAIN, HISTORY, INSTRUME, MACADDR, NAXIS3, OBJECT, ORIGIN, RA, RESTACK, SATMASK, TELESCOP, XBINNING, XPIXSZ, YBINNING, YPIXSZ`

### Signature #4 (947 files, 8.4%)
- **Field Count**: 26
- **Sample Files**: `cb625c_IC 1396_15s60_Duo-Band_20260831-215648047_35C_c.fit, cb625c_IC 1396_15s60_Duo-Band_20260831-220717500_36C_c.fit, cb625c_IC 1396_15s60_Duo-Band_20260831-212104880_35C_c.fit`
- **Extra Fields vs Primary**: `CALMAX, CALMIN, SATMASK`
- **Missing Fields vs Primary**: `APTDIA, BSCALE, BZERO, CAMNAME, CCD-TEMP, COMMENT, DATE, FOCTEMP, FRAME, IMAGETYP, LIVETIME, OFFSET, PROGRAM, ROWORDER, SCALE, XBAYROFF, YBAYROFF`
- **Complete Key Set**: `BAYERPAT, CALMAX, CALMIN, CAMERA, DATE-OBS, DEC, DET-TEMP, EQMODE, EXPTIME, FILTER, FIRMWARE, FOCALLEN, GAIN, HISTORY, INSTRUME, MACADDR, OBJECT, ORIGIN, RA, RESTACK, SATMASK, TELESCOP, XBINNING, XPIXSZ, YBINNING, YPIXSZ`

### Signature #5 (412 files, 3.65%)
- **Field Count**: 24
- **Sample Files**: `NGC 6530 9_15s60_Astro_20260813-235336289_40C.fits, failed_NGC 6530 9_15s60_Astro_20260813-233023546_41C.fits, NGC 6530 9_15s60_Astro_20260813-222600211_40C.fits`
- **Missing Fields vs Primary**: `APTDIA, CAMNAME, CCD-TEMP, COMMENT, DATE, FOCTEMP, FRAME, HISTORY, IMAGETYP, LIVETIME, OFFSET, PROGRAM, ROWORDER, SCALE, XBAYROFF, YBAYROFF`
- **Complete Key Set**: `BAYERPAT, BSCALE, BZERO, CAMERA, DATE-OBS, DEC, DET-TEMP, EQMODE, EXPTIME, FILTER, FIRMWARE, FOCALLEN, GAIN, INSTRUME, MACADDR, OBJECT, ORIGIN, RA, RESTACK, TELESCOP, XBINNING, XPIXSZ, YBINNING, YPIXSZ`

## 3. Master List of Fields Across All Files

Total **197 unique header keywords** identified across all files:

| Field Name | Occurrence Count | Coverage | Sample Values |
|---|---|---|---|
| `APERTURE` | 1808 | 16.03% | `5.0` |
| `APTDIA` | 7058 | 62.57% | `30.0` |
| `AP_0_0` | 35 | 0.31% | `2.26191237591896e-08, 0.000157566026896, 2.5552777010471e-07` |
| `AP_0_1` | 35 | 0.31% | `-3.22475523816297e-10, 5.4029971817e-07, 9.14257909227636e-09` |
| `AP_0_2` | 35 | 0.31% | `-1.48524742093798e-08, 5.9298678528e-07, -6.47201803290788e-08` |
| `AP_0_3` | 14 | 0.12% | `-7.51728993741042e-12, -1.80860945619357e-11, 9.8467945267325e-12` |
| `AP_1_0` | 35 | 0.31% | `-9.2926089045875e-10, -2.77920701383e-07, -2.45790843234062e-08` |
| `AP_1_1` | 35 | 0.31% | `1.21233671491334e-08, 8.20987716779e-07, -6.92880848366817e-09` |
| `AP_1_2` | 14 | 0.12% | `-2.30561774390914e-12, 7.76507423879181e-11, -6.83036124808304e-12` |
| `AP_2_0` | 35 | 0.31% | `-2.68821520120602e-08, -8.73249572694e-07, 1.49922333680081e-08` |
| `AP_2_1` | 14 | 0.12% | `-2.42310633802703e-11, -2.09739813053953e-10, -6.86059827713769e-11` |
| `AP_3_0` | 14 | 0.12% | `-2.03927333988108e-12, 3.92000167086337e-10, 7.36878517462484e-11` |
| `AP_ORDER` | 35 | 0.31% | `3, 2` |
| `A_0_0` | 35 | 0.31% | `0.0, 0` |
| `A_0_1` | 35 | 0.31% | `0.0, 0` |
| `A_0_2` | 35 | 0.31% | `1.48525197838303e-08, -5.94445404846e-07, 6.47157699124615e-08` |
| `A_0_3` | 14 | 0.12% | `7.51757682454007e-12, 1.80843385437479e-11, -9.85736546956569e-12` |
| `A_1_0` | 35 | 0.31% | `0.0, 0` |
| `A_1_1` | 35 | 0.31% | `-1.21185994519175e-08, -8.23545706027e-07, 6.93697520649036e-09` |
| `A_1_2` | 14 | 0.12% | `2.30866924604087e-12, -7.75955823862784e-11, 6.88974058112519e-12` |
| `A_2_0` | 35 | 0.31% | `2.68818637318149e-08, 8.74675392531e-07, -1.4987277275327e-08` |
| `A_2_1` | 14 | 0.12% | `2.42300822736183e-11, 2.09552760856833e-10, 6.85249451995492e-11` |
| `A_3_0` | 14 | 0.12% | `2.04212803002342e-12, -3.91733791984341e-10, -7.36370491698814e-11` |
| `A_ORDER` | 35 | 0.31% | `3, 2` |
| `BAYERPAT` | 11206 | 99.34% | `GRBG, RGGB` |
| `BIAS` | 2 | 0.02% | `467` |
| `BITPIX` | 11280 | 100.0% | `-32, 16` |
| `BP_0_0` | 35 | 0.31% | `-3.27615604570989e-07, 0.000260839507848, -1.44454664358194e-06` |
| `BP_0_1` | 35 | 0.31% | `-9.29623711343197e-10, 6.82208938974e-07, -5.29402466309392e-09` |
| `BP_0_2` | 35 | 0.31% | `-1.27888250204641e-08, 1.06455474949e-06, -1.05296862739184e-07` |
| `BP_0_3` | 14 | 0.12% | `2.0836339643666e-12, 4.45344394695216e-11, -3.26210213079178e-11` |
| `BP_1_0` | 35 | 0.31% | `1.53737372287027e-09, -6.45913434214e-07, 2.68515337848242e-08` |
| `BP_1_1` | 35 | 0.31% | `-9.05519141008288e-10, 7.11593306925e-07, 6.68221894861667e-08` |
| `BP_1_2` | 14 | 0.12% | `-1.4172606823599e-11, 9.02846112344441e-11, 3.33037676993891e-11` |
| `BP_2_0` | 35 | 0.31% | `-2.89286336892028e-09, -1.30560094385e-06, 1.96127330971041e-08` |
| `BP_2_1` | 14 | 0.12% | `2.78638539875096e-11, -1.67735127400004e-11, -5.11065532827687e-11` |
| `BP_3_0` | 14 | 0.12% | `-1.81505470410565e-11, -6.35635358135257e-10, -1.41071215416725e-10` |
| `BP_ORDER` | 35 | 0.31% | `3, 2` |
| `BSCALE` | 9271 | 82.19% | `1.0, 1` |
| `BZERO` | 9271 | 82.19% | `0.0, 32768.0, 32768` |
| `B_0_0` | 35 | 0.31% | `0.0, 0` |
| `B_0_1` | 35 | 0.31% | `0.0, 0` |
| `B_0_2` | 35 | 0.31% | `1.2789156761628e-08, -1.06699806718e-06, 1.05302855217162e-07` |
| `B_0_3` | 14 | 0.12% | `-2.08264175806045e-12, -4.45028757107661e-11, 3.2663329356658e-11` |
| `B_1_0` | 35 | 0.31% | `0.0, 0` |
| `B_1_1` | 35 | 0.31% | `9.04265429919898e-10, -7.15120308382e-07, -6.67838001374404e-08` |
| `B_1_2` | 14 | 0.12% | `1.41699880787233e-11, -9.03557970819413e-11, -3.33514399749141e-11` |
| `B_2_0` | 35 | 0.31% | `2.89487771144707e-09, 1.30839137777e-06, -1.96118852062175e-08` |
| `B_2_1` | 14 | 0.12% | `-2.78596558700538e-11, 1.68713104891653e-11, 5.11645046176814e-11` |
| `B_3_0` | 14 | 0.12% | `1.81486416178895e-11, 6.35320297504197e-10, 1.41044386762192e-10` |
| `B_ORDER` | 35 | 0.31% | `3, 2` |
| `CALMAX` | 1985 | 17.6% | `0.0739717185497284, 0.08879990130662918, 0.07515048235654831` |
| `CALMIN` | 1985 | 17.6% | `0.002059097401797771, 0.00196427060291171, 0.00214617233723402` |
| `CAMERA` | 9367 | 83.04% | `TELE` |
| `CAMNAME` | 7058 | 62.57% | `TELE, WIDE` |
| `CBLACK` | 1 | 0.01% | `13270` |
| `CCD-TEMP` | 8805 | 78.06% | `34.4375, -10.0, 19.3125` |
| `CCDXBIN` | 1793 | 15.9% | `1` |
| `CCDYBIN` | 1793 | 15.9% | `1` |
| `CD1_1` | 68 | 0.6% | `-0.000320596703537266, -0.000634386534225781, -0.000329803066981766` |
| `CD1_2` | 68 | 0.6% | `0.000576369847386787, -0.000180383404138608, 1.13715875584787e-07` |
| `CD2_1` | 68 | 0.6% | `0.000576369847386787, -0.000180383404138608, 1.41634817200265e-07` |
| `CD2_2` | 68 | 0.6% | `0.000320596703537266, 0.000634386534225781, 0.000329814610199463` |
| `CDELT1` | 23 | 0.2% | `-0.000659497688873335, -0.000329801677716994, -0.000329803086586344` |
| `CDELT2` | 23 | 0.2% | `0.000659497688873335, 0.000329817281700592, 0.000329814640611124` |
| `COMMENT` | 8874 | 78.67% | `  FITS (Flexible Image Transport System) format is defined in 'Astronomy, FITS (Flexible Image Transport System) format is defined in 'Astronomy, 7  Solved in 36.6 sec. Offset 177.3d.` |
| `CRBL1X` | 21 | 0.19% | `35, 43, 1642` |
| `CRBL1Y` | 21 | 0.19% | `1079, 1056, 1076` |
| `CRBL2X` | 21 | 0.19% | `0, 40, 273` |
| `CRBL2Y` | 21 | 0.19% | `1079, 890, 822` |
| `CRBR1X` | 21 | 0.19% | `1899, 1843, 1919` |
| `CRBR1Y` | 21 | 0.19% | `1079, 1053, 542` |
| `CRBR2X` | 21 | 0.19% | `1919, 1894, 1438` |
| `CRBR2Y` | 21 | 0.19% | `1079, 890, 822` |
| `CREATOR` | 1794 | 15.9% | `ZWO Seestar S50, ZWO ASIAIR Plus, SetiAstroSuite` |
| `CROTA1` | 1 | 0.01% | `-177.8392827483` |
| `CROTA2` | 1 | 0.01% | `-177.8197512089` |
| `CRPIX1` | 90 | 0.8% | `1667.5, 2583.5, 1966.5` |
| `CRPIX2` | 90 | 0.8% | `1485.5, 2173.5, 2475.5` |
| `CRTL1X` | 21 | 0.19% | `35, 41, 599` |
| `CRTL1Y` | 21 | 0.19% | `95, 73, 533` |
| `CRTL2X` | 21 | 0.19% | `0, 40, 273` |
| `CRTL2Y` | 21 | 0.19% | `40, 0, 130` |
| `CRTR1X` | 21 | 0.19% | `1899, 1841, 877` |
| `CRTR1Y` | 21 | 0.19% | `95, 70, 0` |
| `CRTR2X` | 21 | 0.19% | `1919, 1894, 1438` |
| `CRTR2Y` | 21 | 0.19% | `40, 0, 130` |
| `CRVAL1` | 90 | 0.8% | `306.774349330026, 306.773562936059, 341.746696615716` |
| `CRVAL2` | 90 | 0.8% | `40.1602137085881, 40.168706911981, 58.1080524394849` |
| `CTYPE1` | 90 | 0.8% | `RA---TAN, RA---TAN-SIP` |
| `CTYPE2` | 90 | 0.8% | `DEC--TAN, DEC--TAN-SIP` |
| `CUNIT1` | 87 | 0.77% | `deg` |
| `CUNIT2` | 86 | 0.76% | `deg` |
| `CVF` | 1 | 0.01% | `1.00224268436432` |
| `CWHITE` | 1 | 0.01% | `57253` |
| `DARKTIME` | 71 | 0.63% | `15.0, 60.0, 120.0` |
| `DATAMAX` | 1 | 0.01% | `65535` |
| `DATAMIN` | 1 | 0.01% | `0` |
| `DATE` | 7130 | 63.21% | `2026-07-23T02:04:10, 2026-07-23T00:23:08, 2026-07-19T18:19:08` |
| `DATE-END` | 5 | 0.04% | `2025-03-10T01:09:25.567, 2026-07-21T00:32:05.713` |
| `DATE-EXP` | 1678 | 14.88% | `2026-07-12T06:31:09.975933, 2026-02-26T18:41:59.685369, 2026-08-07T03:29:23.717659` |
| `DATE-OBS` | 11182 | 99.13% | `2026-07-12T06:30:59.068395, 2025-03-10T00:38:34.681000, 2025-07-18T16:29:29.311671` |
| `DEBAYERED` | 1047 | 9.28% | `True` |
| `DEC` | 11181 | 99.12% | `40.030526389815, 40.2067862825972, 40.1405955572883` |
| `DET-TEMP` | 9367 | 83.04% | `42, 41, 35` |
| `EQMODE` | 11127 | 98.64% | `0, 1` |
| `EQUINOX` | 86 | 0.76% | `2000.0` |
| `EXPEND` | 75 | 0.66% | `2461242.85410169, 2461240.90265168, 2461242.52228833` |
| `EXPOSURE` | 1744 | 15.46% | `10.0` |
| `EXPSTART` | 75 | 0.66% | `2461233.77151699, 2461229.84810331, 2461098.27881288` |
| `EXPTIME` | 11267 | 99.88% | `10.0, 180.0, 0.0583330020308495` |
| `EXTEND` | 9276 | 82.23% | `True` |
| `FILENAME` | 2 | 0.02% | `masterDark_BIN-1_4144x2822_EXPOSURE-180.00s.xisf, MasterFlat_58.3ms_-10.0C_gain120_294MC_20250720-200629.fit` |
| `FILTER` | 11185 | 99.16% | `IRCUT, LP, Duo-Band` |
| `FIRMWARE` | 9367 | 83.04% | `1.1.3.2` |
| `FOCALLEN` | 11275 | 99.96% | `251.932258489591, 251.932, 369.0` |
| `FOCPOS` | 65 | 0.58% | `1602, 41408, 1583` |
| `FOCTEMP` | 6996 | 62.02% | `42.0, 41.0, 35.0` |
| `FOCUSPOS` | 1740 | 15.43% | `1622, 1591, 1587` |
| `FRAME` | 7058 | 62.57% | `Light, Bias, Dark` |
| `GAIN` | 11272 | 99.93% | `80, 120, 80.0` |
| `GUIDECAM` | 1 | 0.01% | `ZWO ASI290MM` |
| `HISTORY` | 9117 | 80.82% | `mean stacking with winsorized sigma clipping rejection (low=3.000 high=3, Updated header to FITS_STANDARD.txt for DWARF Mini on 2026-09-11T23:46:3, Updated header to FITS_STANDARD.txt for DWARF Mini on 2026-09-12T00:07:5` |
| `IMAGEH` | 4 | 0.04% | `1920` |
| `IMAGETYP` | 8865 | 78.59% | `Light, Master Dark, Flat` |
| `IMAGEW` | 4 | 0.04% | `1080` |
| `INSTRUME` | 11276 | 99.96% | `Seestar S50, ZWO CCD ASI294MC Pro, ZWO ASI294MC Pro` |
| `LAT-OBS` | 4 | 0.04% | `47.9542` |
| `LATPOLE` | 17 | 0.15% | `0.0` |
| `LIVETIME` | 7126 | 63.17% | `20260.0, 10600.0, 819120.0` |
| `LONG-OBS` | 4 | 0.04% | `14.7906` |
| `LONPOLE` | 85 | 0.75% | `180.0` |
| `MACADDR` | 9367 | 83.04% | `40FDF36A5AEC` |
| `MIPS-FLO` | 66 | 0.59% | `0.0` |
| `MIPS-HI` | 1 | 0.01% | `204` |
| `MIPS-LO` | 1 | 0.01% | `198` |
| `NAXIS` | 11280 | 100.0% | `3, 2` |
| `NAXIS1` | 11280 | 100.0% | `3201, 5346, 3899` |
| `NAXIS2` | 11280 | 100.0% | `2401, 4313, 4852` |
| `NAXIS3` | 1159 | 10.27% | `3, 1080` |
| `NCOMBINE` | 10 | 0.09% | `93, 69, 732` |
| `NSTACK` | 2 | 0.02% | `89` |
| `OBJCTDEC` | 71 | 0.63% | `+40 01 49.895, +40 12 24.431, +40 08 26.144` |
| `OBJCTRA` | 71 | 0.63% | `20 26 21.130, 20 26 53.788, 20 27 11.716` |
| `OBJCTTYP` | 1 | 0.01% | `deepsky` |
| `OBJECT` | 11187 | 99.18% | `Butterfly in Cygnus, NGC 7380, SH2-142` |
| `OBSGEO-B` | 4 | 0.04% | `47.9542` |
| `OBSGEO-L` | 4 | 0.04% | `14.7906` |
| `OFFSET` | 7061 | 62.6% | `30, 467, 0` |
| `ORIGIN` | 9368 | 83.05% | `DWARFLAB, XISF to FITS Converter` |
| `PC1_1` | 22 | 0.2% | `0.365333547265999, 0.99999993947522, 0.999999940556717` |
| `PC1_2` | 22 | 0.2% | `0.930876683155208, -0.000347921766202456, -0.000344799306646318` |
| `PC2_1` | 22 | 0.2% | `-0.930876683155208, 0.000411196933577092, 0.000429437628777865` |
| `PC2_2` | 22 | 0.2% | `0.365333547265999, 0.999999915458537, 0.999999907791657` |
| `PLTSOLVD` | 66 | 0.59% | `True` |
| `PRODUCER` | 1792 | 15.89% | `ZWO` |
| `PROGRAM` | 8870 | 78.63% | `Siril 1.4.4, PixInsight 1.9.4, 5.82` |
| `RA` | 11181 | 99.12% | `306.588040543648, 306.724116507961, 306.798817416124` |
| `RESTACK` | 9367 | 83.04% | `0` |
| `ROWORDER` | 7087 | 62.83% | `TOP-DOWN, BOTTOM-UP` |
| `SATMASK` | 1985 | 17.6% | `1` |
| `SCALE` | 7058 | 62.57% | `3.987786249333333` |
| `SET-TEMP` | 1 | 0.01% | `-10.0` |
| `SIMPLE` | 11280 | 100.0% | `True` |
| `SITELAT` | 1804 | 15.99% | `32.969, 47.9542, 48.8489` |
| `SITELONG` | 1804 | 15.99% | `-96.9821, 14.7906, 8.36972` |
| `STACKCNT` | 126 | 1.12% | `2026, 1060, 10` |
| `STACKED` | 1 | 0.01% | `True` |
| `TELESCOP` | 11276 | 99.96% | `S50_37f824c9, Telescope Simulator, Demo Interface` |
| `TIMESYS` | 4 | 0.04% | `UTC` |
| `TOTALEXP` | 1792 | 15.89% | `10.0, 30.0, 20.0` |
| `WARNING` | 1 | 0.01% | `Warning inexact scale! Set FOV=0.98d or scale=1.2"/pix` |
| `WCSAXES` | 17 | 0.15% | `2` |
| `WIDECAM` | 1760 | 15.6% | `0` |
| `WZCOREX0` | 2 | 0.02% | `1` |
| `WZCOREX1` | 2 | 0.02% | `1919` |
| `WZCOREY0` | 2 | 0.02% | `1` |
| `WZCOREY1` | 2 | 0.02% | `1079` |
| `WZFPRNT` | 9 | 0.08% | `ae92997fde17b7fa, 0050b0a281f62303, e3a093e26040a0d5` |
| `WZNSUBS` | 8 | 0.07% | `93, 69, 732` |
| `XBAYROFF` | 7058 | 62.57% | `0` |
| `XBINNING` | 11276 | 99.96% | `1, 1.0` |
| `XISFCLRS` | 1 | 0.01% | `Gray` |
| `XISFCMPR` | 1 | 0.01% | `` |
| `XISFDIM1` | 1 | 0.01% | `1920` |
| `XISFDIM2` | 1 | 0.01% | `1080` |
| `XISFDIM3` | 1 | 0.01% | `1` |
| `XISFDIMS` | 1 | 0.01% | `3` |
| `XISFFILE` | 1 | 0.01% | `masterDark_BIN-1_1920x1080_EXPOSURE-0.00s.xisf` |
| `XISFGEOM` | 1 | 0.01% | `XISFGeometry(1920:1080:1)` |
| `XISFSAMP` | 1 | 0.01% | `Float32` |
| `XORGSUBF` | 1793 | 15.9% | `0` |
| `XPIXSZ` | 11276 | 99.96% | `2.90000009536743, 4.63, 4.63000011444092` |
| `YBAYROFF` | 7058 | 62.57% | `0` |
| `YBINNING` | 11276 | 99.96% | `1, 1.0` |
| `YORGSUBF` | 1793 | 15.9% | `0` |
| `YPIXSZ` | 11276 | 99.96% | `2.90000009536743, 4.63, 4.63000011444092` |


## 4. Candidates for Standardization

### Exposure Time (Competing Synonyms)
- **Issue**: Multiple fields used for 'Exposure Time' across dataset
- **Competing Fields**: `EXPTIME` (99.88%), `EXPOSURE` (15.46%)
- **Recommendation**: Standardize on primary keyword 'EXPTIME'

### Sensor / Target Temperature (Competing Synonyms)
- **Issue**: Multiple fields used for 'Sensor / Target Temperature' across dataset
- **Competing Fields**: `SET-TEMP` (0.01%), `CCD-TEMP` (78.06%)
- **Recommendation**: Standardize on primary keyword 'SET-TEMP'

### Frame Type (Competing Synonyms)
- **Issue**: Multiple fields used for 'Frame Type' across dataset
- **Competing Fields**: `IMAGETYP` (78.59%), `FRAME` (62.57%)
- **Recommendation**: Standardize on primary keyword 'IMAGETYP'

### Right Ascension (Competing Synonyms)
- **Issue**: Multiple fields used for 'Right Ascension' across dataset
- **Competing Fields**: `RA` (99.12%), `OBJCTRA` (0.63%), `CRVAL1` (0.8%)
- **Recommendation**: Standardize on primary keyword 'RA'

### Declination (Competing Synonyms)
- **Issue**: Multiple fields used for 'Declination' across dataset
- **Competing Fields**: `DEC` (99.12%), `OBJCTDEC` (0.63%), `CRVAL2` (0.8%)
- **Recommendation**: Standardize on primary keyword 'DEC'

### Camera / Instrument (Competing Synonyms)
- **Issue**: Multiple fields used for 'Camera / Instrument' across dataset
- **Competing Fields**: `INSTRUME` (99.96%), `CAMERA` (83.04%)
- **Recommendation**: Standardize on primary keyword 'INSTRUME'

### Software / Publisher (Competing Synonyms)
- **Issue**: Multiple fields used for 'Software / Publisher' across dataset
- **Competing Fields**: `CREATOR` (15.9%), `PROGRAM` (78.63%), `ORIGIN` (83.05%)
- **Recommendation**: Standardize on primary keyword 'SWCREATE'

### Binning (Competing Synonyms)
- **Issue**: Multiple fields used for 'Binning' across dataset
- **Competing Fields**: `XBINNING` (99.96%), `YBINNING` (99.96%)
- **Recommendation**: Standardize on primary keyword 'XBINNING'

### Pixel Size (Competing Synonyms)
- **Issue**: Multiple fields used for 'Pixel Size' across dataset
- **Competing Fields**: `XPIXSZ` (99.96%), `YPIXSZ` (99.96%)
- **Recommendation**: Standardize on primary keyword 'PIXSIZE'

### Site Coordinates (Competing Synonyms)
- **Issue**: Multiple fields used for 'Site Coordinates' across dataset
- **Competing Fields**: `SITELAT` (15.99%), `SITELONG` (15.99%)
- **Recommendation**: Standardize on primary keyword 'SITELAT'

### Observation Date (Competing Synonyms)
- **Issue**: Multiple fields used for 'Observation Date' across dataset
- **Competing Fields**: `DATE-OBS` (99.13%), `DATE` (63.21%)
- **Recommendation**: Standardize on primary keyword 'DATE-OBS'

### Inconsistent Coverage (Fragmented / Optional Metadata)
- **Issue**: 165 header fields appear in <80% of files
- **Recommendation**: Configure acquisition tools to write optional headers consistently

## 5. FITS Editors and Publishers

| Software / Publisher Signature | File Count | Coverage |
|---|---|---|
| DWARFLAB | 9367 | 83.04% |
| DWARF Header Updater v1.1 | 5068 | 44.93% |
| DWARF Header Updater v1.3 | 1976 | 17.52% |
| ZWO Seestar S50 | 1792 | 15.89% |
| 8.46 | 1665 | 14.76% |
| Siril 1.4.4 | 74 | 0.66% |
| 5.82 | 37 | 0.33% |
| 5.50 | 36 | 0.32% |
| Unknown / Unspecified | 11 | 0.1% |
| Siril 1.4.1 | 8 | 0.07% |
| PixInsight | 4 | 0.04% |
| Siril 1.4.0-beta4 | 3 | 0.03% |
| 2.76 | 2 | 0.02% |
| ZWO ASIAIR Plus | 1 | 0.01% |
| PixInsight 1.9.4 | 1 | 0.01% |
| XISF to FITS Converter | 1 | 0.01% |
| SetiAstroSuite | 1 | 0.01% |


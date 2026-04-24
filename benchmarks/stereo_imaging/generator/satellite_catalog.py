"""Vendored satellite inventory for stereo_imaging generator cases.

TLE rows are frozen from CelesTrak Earth Resources GP
(https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle).
Selected for the benchmark horizon near 2026-04-24T00:00:00Z.
The generator writes `dataset/source_data/celestrak/` from this list so dataset
rebuilds do not depend on live element sets or network fetches for TLEs.

Sensor and agility metadata are benchmark numbers and not sourced from the literature. 
They are intended to be representative of the class of sensors and not specific to any particular satellite.
"""

from __future__ import annotations

from typing import Any

# Sorted by norad_catalog_id for stable CSV output and checksums.
CACHED_CELESTRAK_ROWS: list[dict[str, Any]] = [
    {
        "name": "IRS-P5 (CARTOSAT-1)",
        "norad_catalog_id": "28649",
        "tle_line1": "1 28649U 05017A   26114.05326308  .00000820  00000+0  88424-4 0  9992",
        "tle_line2": "2 28649  97.5353 139.5682 0000921 127.8728 232.2574 14.90904401135752",
        "epoch_iso": "2026-04-24T01:16:41.930112Z",
    },
    {
        "name": "ARIRANG-2 (KOMPSAT-2)",
        "norad_catalog_id": "29268",
        "tle_line1": "1 29268U 06031A   26114.27521279  .00000242  00000+0  53929-4 0  9995",
        "tle_line2": "2 29268  97.8316 301.3291 0013061 242.7061 290.3237 14.64624137 53580",
        "epoch_iso": "2026-04-24T06:36:18.385056Z",
    },
    {
        "name": "WORLDVIEW-1 (WV-1)",
        "norad_catalog_id": "32060",
        "tle_line1": "1 32060U 07041A   26114.26743174  .00005315  00000+0  22050-3 0  9996",
        "tle_line2": "2 32060  97.3875 234.7662 0001650 206.5250 153.5903 15.24284132 34661",
        "epoch_iso": "2026-04-24T06:25:06.102336Z",
    },
    {
        "name": "CARTOSAT-2A",
        "norad_catalog_id": "32783",
        "tle_line1": "1 32783U 08021A   26114.26836846 -.00000032  00000+0  25093-5 0  9990",
        "tle_line2": "2 32783  97.7680 164.8062 0010401 290.1957  69.8136 14.79167246970835",
        "epoch_iso": "2026-04-24T06:26:27.034944Z",
    },
    {
        "name": "HUANJING 1A (HJ-1A)",
        "norad_catalog_id": "33320",
        "tle_line1": "1 33320U 08041A   26114.28941049  .00000622  00000+0  80977-4 0  9999",
        "tle_line2": "2 33320  97.6676 102.2249 0018080 319.9932  39.9950 14.83859322950416",
        "epoch_iso": "2026-04-24T06:56:45.066336Z",
    },
    {
        "name": "HUANJING 1B (HJ-1B)",
        "norad_catalog_id": "33321",
        "tle_line1": "1 33321U 08041B   26114.30219766  .00000434  00000+0  58858-4 0  9991",
        "tle_line2": "2 33321  97.6518 105.5691 0036692   2.9387 357.2036 14.83214845950428",
        "epoch_iso": "2026-04-24T07:15:09.877824Z",
    },
    {
        "name": "GEOEYE 1",
        "norad_catalog_id": "33331",
        "tle_line1": "1 33331U 08042A   26114.25198896  .00000358  00000+0  76150-4 0  9997",
        "tle_line2": "2 33331  98.1250 188.8638 0003346 215.2816 144.8165 14.64673209942256",
        "epoch_iso": "2026-04-24T06:02:51.846144Z",
    },
    {
        "name": "THEOS",
        "norad_catalog_id": "33396",
        "tle_line1": "1 33396U 08049A   26114.28138264  .00000149  00000+0  89954-4 0  9995",
        "tle_line2": "2 33396  98.5608 173.3040 0001256  93.4990 266.6331 14.20125575910311",
        "epoch_iso": "2026-04-24T06:45:11.460096Z",
    },
    {
        "name": "DEIMOS-1",
        "norad_catalog_id": "35681",
        "tle_line1": "1 35681U 09041A   26114.26283897  .00000083  00000+0  19378-4 0  9998",
        "tle_line2": "2 35681  97.7346 273.8469 0002172  49.1071 311.0327 14.75176577898938",
        "epoch_iso": "2026-04-24T06:18:29.287008Z",
    },
    {
        "name": "DUBAISAT-1",
        "norad_catalog_id": "35682",
        "tle_line1": "1 35682U 09041B   26114.29652536  .00000873  00000+0  13727-3 0  9990",
        "tle_line2": "2 35682  97.9966 248.1722 0009271 239.9616 120.0673 14.75020417897153",
        "epoch_iso": "2026-04-24T07:06:59.791104Z",
    },
    {
        "name": "WORLDVIEW-2 (WV-2)",
        "norad_catalog_id": "35946",
        "tle_line1": "1 35946U 09055A   26114.23546434  .00000102  00000+0  48337-4 0  9992",
        "tle_line2": "2 35946  98.4693 188.4456 0004830  35.6508 324.5001 14.37927686867892",
        "epoch_iso": "2026-04-24T05:39:04.118976Z",
    },
    {
        "name": "CARTOSAT-2B",
        "norad_catalog_id": "36795",
        "tle_line1": "1 36795U 10035A   26114.27076440 -.00000029  00000+0  32434-5 0  9995",
        "tle_line2": "2 36795  97.9999 165.1511 0011482  12.5834 347.5661 14.78659274851888",
        "epoch_iso": "2026-04-24T06:29:54.044160Z",
    },
    {
        "name": "RASAT",
        "norad_catalog_id": "37791",
        "tle_line1": "1 37791U 11044D   26114.27171134  .00000359  00000+0  70880-4 0  9990",
        "tle_line2": "2 37791  98.0543 206.4992 0020807   7.2765  76.9992 14.68113646785275",
        "epoch_iso": "2026-04-24T06:31:15.859776Z",
    },
    {
        "name": "PLEIADES 1A",
        "norad_catalog_id": "38012",
        "tle_line1": "1 38012U 11076F   26114.27885578  .00000177  00000+0  48010-4 0  9994",
        "tle_line2": "2 38012  98.1981 190.1009 0001065  77.9513  13.0810 14.58535617764135",
        "epoch_iso": "2026-04-24T06:41:33.139392Z",
    },
    {
        "name": "ZIYUAN 1-02C (ZY 1-02C)",
        "norad_catalog_id": "38038",
        "tle_line1": "1 38038U 11079A   26114.30143090  .00000257  00000+0  98679-4 0  9990",
        "tle_line2": "2 38038  98.4093 182.7297 0007661 106.1193 341.6202 14.38168190751466",
        "epoch_iso": "2026-04-24T07:14:03.629760Z",
    },
    {
        "name": "ARIRANG-3 (KOMPSAT-3)",
        "norad_catalog_id": "38338",
        "tle_line1": "1 38338U 12025B   26114.31376920  .00000330  00000+0  74840-4 0  9992",
        "tle_line2": "2 38338  98.1133  72.7191 0004073 289.9137  70.1626 14.62156306743473",
        "epoch_iso": "2026-04-24T07:31:49.658880Z",
    },
    {
        "name": "SPOT 6",
        "norad_catalog_id": "38755",
        "tle_line1": "1 38755U 12047A   26114.27654466  .00000019  00000+0  14062-4 0  9992",
        "tle_line2": "2 38755  98.2139 182.2081 0001235  83.9835 276.1505 14.58520198725194",
        "epoch_iso": "2026-04-24T06:38:13.458624Z",
    },
    {
        "name": "PLEIADES 1B",
        "norad_catalog_id": "39019",
        "tle_line1": "1 39019U 12068A   26114.29591484  .00000079  00000+0  26785-4 0  9992",
        "tle_line2": "2 39019  98.1950 190.0849 0001043  85.4841 274.6477 14.58561361712990",
        "epoch_iso": "2026-04-24T07:06:07.042176Z",
    },
    {
        "name": "GOKTURK 2",
        "norad_catalog_id": "39030",
        "tle_line1": "1 39030U 12073A   26114.30406176 -.00000032  00000+0  22226-5 0  9993",
        "tle_line2": "2 39030  97.6859 314.4273 0001857 103.8744 256.2673 14.75486632716565",
        "epoch_iso": "2026-04-24T07:17:50.936064Z",
    },
    {
        "name": "GAOFEN-1",
        "norad_catalog_id": "39150",
        "tle_line1": "1 39150U 13018A   26114.25567806  .00000771  00000+0  11770-3 0  9997",
        "tle_line2": "2 39150  97.9107 187.4131 0018506  80.6556 279.6746 14.76514172700284",
        "epoch_iso": "2026-04-24T06:08:10.584384Z",
    },
    {
        "name": "VNREDSAT 1",
        "norad_catalog_id": "39160",
        "tle_line1": "1 39160U 13021B   26114.26308832  .00000427  00000+0  88350-4 0  9992",
        "tle_line2": "2 39160  97.9122 169.7368 0001271  87.7289 272.4060 14.64949118692390",
        "epoch_iso": "2026-04-24T06:18:50.830848Z",
    },
    {
        "name": "SKYSAT-A",
        "norad_catalog_id": "39418",
        "tle_line1": "1 39418U 13066C   26114.01931263  .00002667  00000+0  15530-3 0  9997",
        "tle_line2": "2 39418  97.3867 165.1411 0022796 138.8428 221.4528 15.12650859680297",
        "epoch_iso": "2026-04-24T00:27:48.611232Z",
    },
    {
        "name": "DUBAISAT-2",
        "norad_catalog_id": "39419",
        "tle_line1": "1 39419U 13066D   26114.26100384  .00002789  00000+0  17640-3 0  9996",
        "tle_line2": "2 39419  97.4560 105.8406 0010155 211.9306 148.1309 15.09773565678259",
        "epoch_iso": "2026-04-24T06:15:50.731776Z",
    },
    {
        "name": "KAZEOSAT 1",
        "norad_catalog_id": "39731",
        "tle_line1": "1 39731U 14024A   26114.24818600  .00000094  00000+0  41638-4 0  9995",
        "tle_line2": "2 39731  98.3216 188.0314 0001389  99.5008 260.6339 14.42057663630782",
        "epoch_iso": "2026-04-24T05:57:23.270400Z",
    },
    {
        "name": "KAZEOSAT 2",
        "norad_catalog_id": "40010",
        "tle_line1": "1 40010U 14033A   26114.27322035  .00000575  00000+0  72581-4 0  9997",
        "tle_line2": "2 40010  97.5453 316.7232 0009648 129.5495 230.6575 14.85405179640952",
        "epoch_iso": "2026-04-24T06:33:26.238240Z",
    },
    {
        "name": "HODOYOSHI-4",
        "norad_catalog_id": "40011",
        "tle_line1": "1 40011U 14033B   26114.23964823  .00000288  00000+0  36902-4 0  9999",
        "tle_line2": "2 40011  97.5465 301.6697 0024901 122.2235 238.1401 14.87990268640787",
        "epoch_iso": "2026-04-24T05:45:05.607072Z",
    },
    {
        "name": "DEIMOS-2",
        "norad_catalog_id": "40013",
        "tle_line1": "1 40013U 14033D   26114.25472532  .00000902  00000+0  90694-4 0  9995",
        "tle_line2": "2 40013  97.5893 350.6218 0001909 102.9371 257.2062 14.93566883629675",
        "epoch_iso": "2026-04-24T06:06:48.267648Z",
    },
    {
        "name": "HODOYOSHI-3",
        "norad_catalog_id": "40015",
        "tle_line1": "1 40015U 14033F   26114.02222821  .00000872  00000+0  10674-3 0  9991",
        "tle_line2": "2 40015  97.6371 279.2629 0033231 170.5361 189.6488 14.85262353639581",
        "epoch_iso": "2026-04-24T00:32:00.517344Z",
    },
    {
        "name": "SPOT 7",
        "norad_catalog_id": "40053",
        "tle_line1": "1 40053U 14034A   26114.27980034  .00000154  00000+0  40654-4 0  9993",
        "tle_line2": "2 40053  98.0658 178.1521 0001589  78.9103 281.2277 14.60908833629262",
        "epoch_iso": "2026-04-24T06:42:54.749376Z",
    },
    {
        "name": "SKYSAT-B",
        "norad_catalog_id": "40072",
        "tle_line1": "1 40072U 14037D   26113.58770957  .00000978  00000+0  11362-3 0  9998",
        "tle_line2": "2 40072  98.3797  69.4620 0007017  94.1673 266.0344 14.87876792637842",
        "epoch_iso": "2026-04-23T14:06:18.106848Z",
    },
    {
        "name": "WORLDVIEW-3 (WV-3)",
        "norad_catalog_id": "40115",
        "tle_line1": "1 40115U 14048A   26114.26139334  .00000689  00000+0  87180-4 0  9993",
        "tle_line2": "2 40115  97.8579 189.8383 0002768 112.4313 247.7195 14.84928730633908",
        "epoch_iso": "2026-04-24T06:16:24.384576Z",
    },
    {
        "name": "GAOFEN-2",
        "norad_catalog_id": "40118",
        "tle_line1": "1 40118U 14049A   26114.32389339  .00000172  00000+0  29228-4 0  9992",
        "tle_line2": "2 40118  98.0137 178.5746 0008520  54.0613 306.1389 14.80833995631264",
        "epoch_iso": "2026-04-24T07:46:24.388896Z",
    },
    {
        "name": "ASNARO",
        "norad_catalog_id": "40298",
        "tle_line1": "1 40298U 14070A   26114.29356267  .00006153  00000+0  29210-3 0  9990",
        "tle_line2": "2 40298  97.3453 191.8532 0003069  24.8285 335.3098 15.19594125635829",
        "epoch_iso": "2026-04-24T07:02:43.814688Z",
    },
    {
        "name": "CBERS 4",
        "norad_catalog_id": "40336",
        "tle_line1": "1 40336U 14079A   26114.29709541 -.00000148  00000+0 -36951-4 0  9990",
        "tle_line2": "2 40336  98.3390 172.8298 0001232 133.2408 226.8881 14.35543694596229",
        "epoch_iso": "2026-04-24T07:07:49.043424Z",
    },
    {
        "name": "KOMPSAT-3A",
        "norad_catalog_id": "40536",
        "tle_line1": "1 40536U 15014A   26114.23669984  .00027133  00000+0  42987-3 0  9998",
        "tle_line2": "2 40536  97.6905 101.7641 0059942  16.1379 344.1763 15.51290459613449",
        "epoch_iso": "2026-04-24T05:40:50.866176Z",
    },
    {
        "name": "GAOFEN-8",
        "norad_catalog_id": "40701",
        "tle_line1": "1 40701U 15030A   26114.26509765  .00010805  00000+0  23871-3 0  9992",
        "tle_line2": "2 40701  97.6938 304.4740 0009610  36.0471 324.1422 15.44001706603123",
        "epoch_iso": "2026-04-24T06:21:44.436960Z",
    },
    {
        "name": "CARBONITE 1 (CBNT-1)",
        "norad_catalog_id": "40718",
        "tle_line1": "1 40718U 15032D   26114.29034138  .00000701  00000+0  91377-4 0  9993",
        "tle_line2": "2 40718  97.6501 294.6247 0015920 109.2764 251.0174 14.83409660581353",
        "epoch_iso": "2026-04-24T06:58:05.495232Z",
    },
    {
        "name": "GAOFEN-9 01",
        "norad_catalog_id": "40894",
        "tle_line1": "1 40894U 15047A   26114.28092965  .00000720  00000+0  94833-4 0  9996",
        "tle_line2": "2 40894  97.6329 152.4138 0026289 319.4468  40.4787 14.82783212572203",
        "epoch_iso": "2026-04-24T06:44:32.321760Z",
    },
    {
        "name": "ZIYUAN 3-02 (ZY 3-02)",
        "norad_catalog_id": "41556",
        "tle_line1": "1 41556U 16033A   26114.32177485  .00004353  00000+0  19754-3 0  9998",
        "tle_line2": "2 41556  97.3844 191.1239 0014120 120.4449 239.8183 15.21242657549799",
        "epoch_iso": "2026-04-24T07:43:21.347040Z",
    },
    {
        "name": "CARTOSAT-2C",
        "norad_catalog_id": "41599",
        "tle_line1": "1 41599U 16040A   26114.24975796  .00003691  00000+0  17838-3 0  9990",
        "tle_line2": "2 41599  97.4515 174.9552 0008648 327.3155  32.7544 15.19222862545520",
        "epoch_iso": "2026-04-24T05:59:39.087744Z",
    },
    {
        "name": "SKYSAT-C1",
        "norad_catalog_id": "41601",
        "tle_line1": "1 41601U 16040C   26113.74734516  .00006292  00000+0  18534-3 0  9995",
        "tle_line2": "2 41601  96.9621 148.4406 0002188 170.9495 189.1789 15.35364564549517",
        "epoch_iso": "2026-04-23T17:56:10.621824Z",
    },
    {
        "name": "SKYSAT-C4",
        "norad_catalog_id": "41771",
        "tle_line1": "1 41771U 16058B   26114.02285949  .00012347  00000+0  24710-3 0  9996",
        "tle_line2": "2 41771  96.9225 138.1180 0003610  98.1969 261.9692 15.46884541537094",
        "epoch_iso": "2026-04-24T00:32:55.059936Z",
    },
    {
        "name": "SKYSAT-C5",
        "norad_catalog_id": "41772",
        "tle_line1": "1 41772U 16058C   26114.02922627  .00005668  00000+0  17634-3 0  9993",
        "tle_line2": "2 41772  97.0529 157.1019 0004882 116.0941 244.0806 15.33670184535446",
        "epoch_iso": "2026-04-24T00:42:05.149728Z",
    },
    {
        "name": "SKYSAT-C2",
        "norad_catalog_id": "41773",
        "tle_line1": "1 41773U 16058D   26113.98860227  .00008958  00000+0  22039-3 0  9995",
        "tle_line2": "2 41773  97.0223 138.1619 0001783 207.3904 152.7250 15.40828801536700",
        "epoch_iso": "2026-04-23T23:43:35.236128Z",
    },
    {
        "name": "SKYSAT-C3",
        "norad_catalog_id": "41774",
        "tle_line1": "1 41774U 16058E   26114.02641491  .00016388  00000+0  29093-3 0  9995",
        "tle_line2": "2 41774  96.9102 147.0205 0002720 106.1034 254.0518 15.50274923537713",
        "epoch_iso": "2026-04-24T00:38:02.248224Z",
    },
    {
        "name": "GOKTURK 1A",
        "norad_catalog_id": "41875",
        "tle_line1": "1 41875U 16073A   26114.27519289  .00000267  00000+0  61437-4 0  9998",
        "tle_line2": "2 41875  98.1299   9.7781 0001419  81.0460 279.0903 14.62791497500949",
        "epoch_iso": "2026-04-24T06:36:16.665696Z",
    },
    {
        "name": "CARTOSAT-2D",
        "norad_catalog_id": "41948",
        "tle_line1": "1 41948U 17008A   26114.28266123  .00002236  00000+0  10930-3 0  9994",
        "tle_line2": "2 41948  97.4146 174.5804 0005762  76.3771 283.8105 15.19251804509398",
        "epoch_iso": "2026-04-24T06:47:01.930272Z",
    },
    {
        "name": "CARTOSAT-2E",
        "norad_catalog_id": "42767",
        "tle_line1": "1 42767U 17036C   26114.23394477  .00000291  00000+0  16977-4 0  9991",
        "tle_line2": "2 42767  97.4313 174.9111 0004138 127.6472 232.5139 15.19284933489959",
        "epoch_iso": "2026-04-24T05:36:52.828128Z",
    },
    {
        "name": "FORMOSAT-5",
        "norad_catalog_id": "42920",
        "tle_line1": "1 42920U 17049A   26114.26103953  .00000128  00000+0  43412-4 0  9999",
        "tle_line2": "2 42920  98.2261 190.7662 0010272 245.6722 114.3401 14.50876725458857",
        "epoch_iso": "2026-04-24T06:15:53.815392Z",
    },
    {
        "name": "SKYSAT-C11",
        "norad_catalog_id": "42987",
        "tle_line1": "1 42987U 17068A   26113.92453353  .00020310  00000+0  30342-3 0  9999",
        "tle_line2": "2 42987  97.4286 260.5349 0001469 144.7507 215.3845 15.55064746474809",
        "epoch_iso": "2026-04-23T22:11:19.696992Z",
    },
]

_SENSOR_PROFILES: dict[str, dict[str, float | int]] = {
    "very_high_resolution_agile": {
        "pixel_ifov_deg": 0.000035,
        "cross_track_pixels": 30000,
        "max_off_nadir_deg": 35.0,
        "max_slew_velocity_deg_per_s": 2.0,
        "max_slew_acceleration_deg_per_s2": 0.95,
        "settling_time_s": 1.5,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    "pleiades_agile": {
        "pixel_ifov_deg": 0.00004,
        "cross_track_pixels": 20000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.95,
        "max_slew_acceleration_deg_per_s2": 0.95,
        "settling_time_s": 1.9,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    "spot_agile": {
        "pixel_ifov_deg": 0.00012,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 2.35,
        "max_slew_acceleration_deg_per_s2": 1.15,
        "settling_time_s": 1.35,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    "cartosat_agile": {
        "pixel_ifov_deg": 0.00005,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.2,
        "max_slew_acceleration_deg_per_s2": 0.4,
        "settling_time_s": 2.5,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    "medium_resolution_agile": {
        "pixel_ifov_deg": 0.000065,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.4,
        "max_slew_acceleration_deg_per_s2": 0.65,
        "settling_time_s": 2.0,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    "wide_swath_agile": {
        "pixel_ifov_deg": 0.00022,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.95,
        "max_slew_acceleration_deg_per_s2": 0.95,
        "settling_time_s": 1.9,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
}

_SATELLITE_ID_OVERRIDES: dict[int, str] = {
    28649: "sat_cartosat_1",
    32060: "sat_worldview_1",
    33331: "sat_geoeye_1",
    35946: "sat_worldview_2",
    36795: "sat_cartosat_2b",
    38012: "sat_pleiades_1a",
    38338: "sat_kompsat_3",
    38755: "sat_spot_6",
    39019: "sat_pleiades_1b",
    39731: "sat_kazeosat_1",
    40010: "sat_kazeosat_2",
    40013: "sat_deimos_2",
    40053: "sat_spot_7",
    40115: "sat_worldview_3",
    40118: "sat_gaofen_2",
    40536: "sat_kompsat_3a",
    41556: "sat_ziyuan_3_02",
    41599: "sat_cartosat_2c",
}

_PROFILE_OVERRIDES_BY_NORAD: dict[int, str] = {
    28649: "cartosat_agile",
    32060: "very_high_resolution_agile",
    33331: "very_high_resolution_agile",
    35946: "very_high_resolution_agile",
    36795: "cartosat_agile",
    38012: "pleiades_agile",
    38338: "medium_resolution_agile",
    38755: "spot_agile",
    39019: "pleiades_agile",
    39731: "medium_resolution_agile",
    40010: "wide_swath_agile",
    40013: "wide_swath_agile",
    40053: "spot_agile",
    40115: "very_high_resolution_agile",
    40118: "medium_resolution_agile",
    40536: "medium_resolution_agile",
    41556: "medium_resolution_agile",
    41599: "cartosat_agile",
}


def _slug_from_name(name: str) -> str:
    slug_chars: list[str] = []
    previous_underscore = False
    for char in name.lower():
        if "a" <= char <= "z" or "0" <= char <= "9":
            slug_chars.append(char)
            previous_underscore = False
        elif not previous_underscore:
            slug_chars.append("_")
            previous_underscore = True
    slug = "".join(slug_chars).strip("_")
    return f"sat_{slug}"


def _profile_for_satellite(norad_catalog_id: int, name: str) -> str:
    if norad_catalog_id in _PROFILE_OVERRIDES_BY_NORAD:
        return _PROFILE_OVERRIDES_BY_NORAD[norad_catalog_id]
    normalized = name.lower()
    if "worldview" in normalized or "geoeye" in normalized:
        return "very_high_resolution_agile"
    if "pleiades" in normalized:
        return "pleiades_agile"
    if "spot" in normalized:
        return "spot_agile"
    if "cartosat" in normalized:
        return "cartosat_agile"
    if "deimos" in normalized or "kazeosat" in normalized:
        return "wide_swath_agile"
    return "medium_resolution_agile"


def _build_satellite_catalog() -> dict[int, dict[str, Any]]:
    catalog: dict[int, dict[str, Any]] = {}
    used_ids: set[str] = set()
    for row in CACHED_CELESTRAK_ROWS:
        norad = int(row["norad_catalog_id"])
        sat_id = _SATELLITE_ID_OVERRIDES.get(norad, _slug_from_name(str(row["name"])))
        if sat_id in used_ids:
            sat_id = f"{sat_id}_{norad}"
        used_ids.add(sat_id)
        profile_name = _profile_for_satellite(norad, str(row["name"]))
        catalog[norad] = {
            "id": sat_id,
            **_SENSOR_PROFILES[profile_name],
        }
    return catalog


SATELLITE_CATALOG: dict[int, dict[str, Any]] = _build_satellite_catalog()

__all__ = ["CACHED_CELESTRAK_ROWS", "SATELLITE_CATALOG"]

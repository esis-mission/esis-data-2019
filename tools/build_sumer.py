"""
Build the archive of the SUMER spectra which the training set of the
neural-network inversion of ESIS is drawn from.

The archive holds level-1 files of the Solar Ultraviolet Measurements of
Emitted Radiation (SUMER) spectrograph on the Solar and Heliospheric
Observatory (SOHO), each a gzipped tar of FITS files, exactly as the SOHO
archive serves them. They are the files of every observation whose rasters of
O V 629.7 Angstrom passed our survey of the SOHO archive for that training set,
kept here so that the training set can be built again if the SOHO archive goes
away. Which of their rasters the training set uses, and how it cleans them, is
left to the code which builds it.

A manifest records where each file came from, its size and SHA-256 checksum,
and its observation in ESA's catalogue of SOHO.

Run it as ``python tools/build_sumer.py <directory> [<source>]``. It takes each
file listed in :data:`files` from ``<source>`` if it is there, and downloads it
from the SOHO archive otherwise; checks it against its checksum, against its
size in the catalogue, and by reading it through; and writes
``<directory>/manifest.csv`` beside the files.

The files are released one by one, not packed into one archive, since together
they are larger than GitHub allows a file of a release to be, and so that a
user can download only those they need.
"""

import csv
import hashlib
import pathlib
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

url_archive = (
    "https://sohodata.nascom.nasa.gov/archive/soho/private/data/processed/sumer/L1"
)
"""
The directory of the SOHO archive which holds the level-1 files of SUMER, in
one directory per year.
"""

url_tap = "https://ssa.esac.esa.int/ssa-sl-tap/tap/sync"
"""The TAP service of ESA's SOHO Science Archive, which holds its catalogue."""

columns = {
    "file_name": "o",
    "file_size": "o",
    "begin_date": "o",
    "end_date": "o",
    "observation_name": "s",
    "science_objective": "o",
    "exposure_times": "s",
    "position_of_fov": "s",
    "size_of_fov": "s",
    "wavelength_range": "o",
}
"""
The columns asked of the catalogue, and the table of each: ``o`` for
``soho.observation``, which describes every file of SOHO, and ``s`` for
``soho.sumer_observation``, which adds what is particular to SUMER.
"""

keys = tuple(k for k in columns if k not in ("file_name", "file_size"))
"""The columns of the catalogue copied into the manifest."""

name_manifest = "manifest.csv"
"""The name of the manifest."""

files: dict[str, str] = {
    "sum_19960330_055740_l1.tgz": "ca54904b8e6a2fcf285c37cb90d630dc54a7609b76fd98cd5f4c21763402165e",
    "sum_19960330_113703_l1.tgz": "be99c8cb1013723d6de63cf353d7d15a0219a123db1592ac8943162c3b3629e7",
    "sum_19960401_051612_l1.tgz": "cf24465ed0d8fe1305b81d6410bd31b330c55623a7d657aa73c92d10ece30535",
    "sum_19960402_120242_l1.tgz": "46b08d690f23e06ba8c6a9ed1f80e455e9e3ab2c2c1cb795e5a31f19298fbf15",
    "sum_19960402_180130_l1.tgz": "f2cf1ee0102b14804f23f01f674e8e1e1183a3d1adfdeeffefe8a91a48a16b86",
    "sum_19960402_225025_l1.tgz": "68610e4af03646590a49b1080f5e9d939075c88b4dab3cfd751c6d6b04ee2761",
    "sum_19960403_071008_l1.tgz": "f66bb651cec5dcaf0d837da237035f7d3548f6d2ae99a16e42cd26b30a5d70d7",
    "sum_19960406_021022_l1.tgz": "7aadfe03131eb3bb7feb3a88d35e1fd3c5bf1c0f87fc8e0d3bde2d46a9d8a805",
    "sum_19960416_082110_l1.tgz": "082e3114220a3e7c114434ac7dca792a746234b540af1c86d5467a0f530669c2",
    "sum_19960419_050303_l1.tgz": "63adde140baecc74ef3926eef59cd2f427a58852e8701a1b5bc218effac916be",
    "sum_19960429_205926_l1.tgz": "9d89c776758234d087617bb7359d7d935f4ae0db4ae599795e24f28813e9930c",
    "sum_19960507_163919_l1.tgz": "a48d900831bb249e3296084b110d80564fb0f8db1554c2a0b80abaf6de1ce7d5",
    "sum_19960509_104137_l1.tgz": "8374a72ab276c63cc61d9b6111169f666fd11ec6c5eec73bf3a59ece1269e65b",
    "sum_19960510_072515_l1.tgz": "08b852a110682ab939674ad9c3b01d89bd15f6008eccf6e459ee820ce692e053",
    "sum_19960510_205437_l1.tgz": "90bb341a6d87f3a4b3999c5b76b18399c2d8aabbdfff2844ef585a440b05913a",
    "sum_19960525_131133_l1.tgz": "0b85340ef45463cff5d5e23bd18f840c5447a7f9a8ddce318e7267aa2f8ab098",
    "sum_19960602_155827_l1.tgz": "021a47f208a2be913ca385567627305c6d131c71d65303d5e485f1e7247001a5",
    "sum_19960605_205651_l1.tgz": "f3a4774651daef3e02aee07e116412a0556feaa683ccd96313496144d02c9881",
    "sum_19960608_150320_l1.tgz": "6ef515779d65ae2aab49a8d6ee5c68b804bbf7e586c8d02b0e763539ca4ee8ff",
    "sum_19960608_173930_l1.tgz": "6e18bd7bd869fe9155de73a4a6b9710dd8a26bc9a28a19506339aeae72d1956a",
    "sum_19960609_150220_l1.tgz": "c64b69b6bf6614d90d4ba2f161b230b4ff905c54957e16475ed80f67292626b7",
    "sum_19960609_173819_l1.tgz": "6aade616cc374ba19fbbe6cac0852017a9561f9d9b1c64891f6b2f4d1c7fe67a",
    "sum_19960609_203113_l1.tgz": "e8e22d672a89abad38ae333adda731cde460de66de25bdb1453f78b328f7e219",
    "sum_19960611_080116_l1.tgz": "dd163d44bdd6be64adadacc61d7e72bd5e557c9f5fdcedb1207b6bf7c204278c",
    "sum_19960614_163131_l1.tgz": "3db096c7cb5fb41d210cf3b7d011df95977171cdfe0af46a1866d6d872b9953f",
    "sum_19960615_061908_l1.tgz": "ceaa81a91a148664341745889b7236c4517afe1fbcfd4216b000baa7f2840624",
    "sum_19960615_164610_l1.tgz": "9c942bc4b5b1a3b3f8554733ef0df07538c86c47d47967d87f99817f18a954e0",
    "sum_19960616_164538_l1.tgz": "8f857bd67a79b77fa8eac6e20bee04e537ab7fb4c27803e1bb4f8fe91f52c106",
    "sum_19960617_073103_l1.tgz": "db4f91c7ff2f2b84284f1e408227694abe011d8020c24237413143f6b2cb000b",
    "sum_19960622_234412_l1.tgz": "60e61f1f14abb328be9f0308f8487ade65895e920cb76674ecb28742a8c5d7a4",
    "sum_19960623_164926_l1.tgz": "6a468ee0926956bfca5aabcffb0758027c69fa8d5f7a21047ab4eee6e85b8023",
    "sum_19960623_224719_l1.tgz": "e44331efa5679a1ce97474f510b8be312096606cfb72ebed07950651e0dfec85",
    "sum_19960625_073056_l1.tgz": "07d7cbab8a7920031d588b62e04f824e95c05f7ae4b4263923d5625e21506006",
    "sum_19960722_070324_l1.tgz": "54edfbec447001485826903a1849d59a4306af319aa7a6e14d9f9a3a71421e5e",
    "sum_19960723_065902_l1.tgz": "1c7f22f6f4d139fa565232f179b98ec61c3cd578c9e3b3982f320fa9ad98b7d1",
    "sum_19960724_100020_l1.tgz": "ae81c658adce18eb2eef8d1209ca2ab3eb1445a4eab56a52a65395c166c790e8",
    "sum_19960725_083611_l1.tgz": "27e0da5d125e1a0845697cf99c2b408380dd324e56265870fcb08f234727db8c",
    "sum_19960726_090342_l1.tgz": "2a7e67e7548fcb1590a1dd6c442d9789b6123deae2635fff8b29ca4bc756eb9f",
    "sum_19960727_231635_l1.tgz": "41fe74316a3489b3d76fd822ad3db8094ebab56f829a88b7e7710e5f0c59e70b",
    "sum_19960728_072013_l1.tgz": "2343366c3f7e2d2b9b1ecfe3a0c13869083eaf6dcff89fcdaef15fb7aa075fb3",
    "sum_19960728_165139_l1.tgz": "2b5e62a21a35da8b7c5802c05a7052d06d4157fd8b51b138ca3f5286231154cd",
    "sum_19960729_005507_l1.tgz": "f6ec45fc41c58f1514d998c882406d43bbeb3f07c93850c455ab413693a7f813",
    "sum_19960802_111734_l1.tgz": "0d071ffb66dc63addaa75391ae5f69829bd4acf784243b578a793e99a7ee5f88",
    "sum_19960806_103819_l1.tgz": "079e7355b33bb817dbede1faefb058d35b2053a07d60862877efe26b7e834965",
    "sum_19960809_011538_l1.tgz": "98d09497e79c4bc92ca053ee00541920b3cf80b9ef12347b8ae8b445204af9c3",
    "sum_19960810_000334_l1.tgz": "11f7eedc7c8c73aa7918833b7dcbd08fcc44d19e320a2a75f8293f2ab0a2d38b",
    "sum_19960810_080829_l1.tgz": "e819d29372844981094e3de529ffac31007d4fe5ae566ffc2055b673118eabf1",
    "sum_19960811_000343_l1.tgz": "4f795d32e1771da19c764675f07f0af50ecc27224420082f334f4c65fd6d5d04",
    "sum_19960811_081014_l1.tgz": "8543e0c174fb2bd6d0945905603ab6cb2190c87234db4d0aaa673f0be6a4c436",
    "sum_19960812_053142_l1.tgz": "ec5a4039e9f89e5f858e972704238f7276dda99e5ff8a46c7a4587b854e6deaf",
    "sum_19960813_050142_l1.tgz": "c74ddb86d1dd429568a65aa2a4b913ab260bb821cb314e94c5371abcfc5203b4",
    "sum_19960813_130958_l1.tgz": "4045b8228ee815f086b886cffc627b8240f48da317c8c317d60c0044e68fc03e",
    "sum_19960815_060138_l1.tgz": "7471ec8b18acda130a396bdbc8d82dbae34d65cdcd19636e31bb1075fe4256fb",
    "sum_19960816_020112_l1.tgz": "79066c5f085accf7a86138eb9167bb52e94f7200b87e055b875ae6af09f0bca8",
    "sum_19960817_050118_l1.tgz": "c9cfb2d8c42fe9f90f9b26f3199a0ee8cc1d8b2b3b15f40aa5b6b529dd574875",
    "sum_19960817_170108_l1.tgz": "197627e91bc5d220db1eac908785761fa19ac5fc2a5da3bfea2791af450c3756",
    "sum_19960818_054620_l1.tgz": "8be6457d404d224a45bd46dba74510ac19232a9e688a971a89e2f9a9ad1c2396",
    "sum_19960818_170116_l1.tgz": "343eb4303a1c0fea6418001c8950fe7800eed6a950b53660c50bdf08b0d83ade",
    "sum_19960819_061627_l1.tgz": "cace46c4759ed1e4c24d4352bcb6a8308efbd7f4bf451e489ffe13573d7596d3",
    "sum_19960820_132907_l1.tgz": "08244d3e81d43daa7f3753983e27092b1f04bbda7cd8f411f9881ab844a08a5d",
    "sum_19960821_232140_l1.tgz": "4bbbaa3dd15e61da79d3b775fa0db86aed7acf6df3ae290e4640a85d91d7e2f8",
    "sum_19960822_230125_l1.tgz": "60e44787a2fa7c8e87a30b6ebe11b9f574494b858d6d09dbcbaf0d260d8d3ef0",
    "sum_19960824_160116_l1.tgz": "92ad49a13aea8a4883898f3cb18692dc7ba41c5f2e24db90335e278befc59fc1",
    "sum_19960825_000457_l1.tgz": "27498f20976f601ee6c37e8d9b77551ba3d77bff6438370d9c84f1f6f470b408",
    "sum_19960825_080848_l1.tgz": "c19416ef7fd6190c5f6ae6c3c5848d883ebf57d01fb8b409f13c5c6ead50d940",
    "sum_19960825_161230_l1.tgz": "b446a9e44304cd5214ad6697730e986df2a9bb468d12f7781db0e09c1a00a070",
    "sum_19960826_001611_l1.tgz": "b1e52d48644828b627b7da8eb5973613731127b05289f137da6f0febaa5cc218",
    "sum_19960829_030311_l1.tgz": "fdd76a45afe25f59b19364166b70aa561a400ba19600ab27551860aee01c2d17",
    "sum_19960830_010112_l1.tgz": "5d997f71640d6cf60e4ad93c6c1d74bcf7e800b1793c4ba3c88e7a652c224a38",
    "sum_19960831_160039_l1.tgz": "46ed2bbee626b018eb719c7dc25af5b29bbff1326c3c3f11f65d4be683adb373",
    "sum_19960901_000321_l1.tgz": "3fe0bf8362fbbfc5486dd1011c9bd63ce54f9fa96f8879cc95a930915afc60d9",
    "sum_19960901_080436_l1.tgz": "8ab58e8d2f0fbf15a87a3d3bef17470755290e402ab537b9d68901abefc4a613",
    "sum_19960901_160027_l1.tgz": "c7d90cab8f1ad43f6b87db2b81044dc11b2dc6df1edc5f41fa4621910d3dadd2",
    "sum_19960904_033413_l1.tgz": "3847eca54f4f949ab93413afde5c5378a66b934820d67e5afd01931137822c57",
    "sum_19960905_054217_l1.tgz": "16a9b52bd427513b0cc4615c1b115ec65eb3312818c0da69458134a68f9b2b56",
    "sum_19960906_173109_l1.tgz": "39b10ab5911b3234ad16d851360882a4ed96362c99330e12086c0dd6135467c6",
    "sum_19960907_172803_l1.tgz": "51cc35603708f221536a6766474f2d4fe4b3369b4c1326e977cfbf74eb596575",
    "sum_19960908_013211_l1.tgz": "3db51fa041af5386d71875f5d666287b282ed06b7546bbc74114aff0f5a99aec",
    "sum_19960908_152426_l1.tgz": "ae5611a4417792f8755233256758a5c9029ec7e6487c9a3127484563933a3fa4",
    "sum_19960908_232834_l1.tgz": "8432e6cf20b2e57aeae454c32c7720c7d552dac6a0fed3600f2e3145b04f39f6",
    "sum_19960914_070110_l1.tgz": "32bbea9cdd2eafc2679998888db6734022f89520e774f1ec3b731eeb818ee4d1",
    "sum_19960916_070058_l1.tgz": "1328eca847a1d2e648f2f29bf7f9b6725f7414e74ff2729ae0c22c86e07cbd76",
    "sum_19960916_160201_l1.tgz": "e37403c3caf489ad3ddd5f9f503ae251c64f099bc3cca3861de126d1cf2d7086",
    "sum_19960919_224958_l1.tgz": "cf8f2c3df273c495518ecee7bbde21d0c2883fa7f62ba61bffa506a117e074a6",
    "sum_19960920_014850_l1.tgz": "3608683ec6dd58f65a1dd3262386e627e0329ec6766696270324c1e7fac6a46a",
    "sum_19960920_192202_l1.tgz": "4ef989eadb31e13e5a760ceff27a71f9500f3b765f0dfe294b73c3376f4ad9a7",
    "sum_19960920_222052_l1.tgz": "da599eaaff888c795e0166d5b0c4d156952d48d29d8937618ec38583d8f08ba6",
    "sum_19960928_151003_l1.tgz": "600f4e26a8e7a2d24c60c62fd821e7cc48359c8d93bee392fa3e97676ac37602",
    "sum_19961002_140055_l1.tgz": "49642ce088e8d48722279b44673710a0f05d2ec469bbd654aae1f7c98378d45c",
    "sum_19961002_155401_l1.tgz": "27a6c129d1a60abcfd4e0e951280a6db2693a03b87b68dc48e936a50ad2c6595",
    "sum_19961008_063345_l1.tgz": "bef321a49914cdde1ba3cdda42c8c627eba64d381ec25b7f12564a1ecc19a740",
    "sum_19961012_154450_l1.tgz": "54c1beebf280dac001f80e4ee485763d093e3d5737d90078dc22dd4f1544343f",
    "sum_19961012_184446_l1.tgz": "d8241cf1f656e3d2da6cebd4ea7e2117b28842612ff731301dc98dc8d841124d",
    "sum_19961015_074217_l1.tgz": "eac590067c4bb6706fd7997a931377eeec5b101e3c8b29df02d621356f0db08d",
    "sum_19970423_080043_l1.tgz": "3b17c1d2ba9cedebfa6006536e7039584aac5d7724994b407b5ff8cc1a368197",
    "sum_19990227_050118_l1.tgz": "c7ff81901b407e882b058a8ba4beb3bf72c9eb5006e5437bbc48cdbec0cbc95e",
    "sum_19990227_061355_l1.tgz": "0066a1e6a99418d8476793af3f6bf4a4d48bd75946b9914a3a4c15c71df845a0",
    "sum_19990227_072636_l1.tgz": "2d2fae61d046e11e3a9cfad90c30fc8c567f237cf0e6dbd40bfc83b5cce3ecfb",
    "sum_19990316_163005_l1.tgz": "119fab4de17fade561ec86a144d3fd17aa354ff3aec434391cd9e35986095506",
    "sum_19990318_154814_l1.tgz": "cb975e96cd5254382163af39a7da80e3923eda89090eb91c9f9ce000cd6adaa7",
    "sum_19990319_165622_l1.tgz": "cb557238ed3e402d579827a54410b8ac4eefb51d4210eff340822080ee7364f1",
    "sum_19991014_195709_l1.tgz": "2e1c3f8c8b2da6db8d8961fd4d9f9204046fbcb8f95c4fafd5dfbe62dc1c547a",
    "sum_19991014_205905_l1.tgz": "4570790dc34368349cbde6080e737ef3e996886d30124d0e8f0ce8a72ee5f710",
    "sum_20041130_122451_l1.tgz": "f3539cf6e73e48f90fbdbf10785eb935f447d3596faa78407f521d36cef17e21",
    "sum_20041205_203240_l1.tgz": "47a98d226228dd798ca5705a952bfc882174c4d9d3ed1fc6400ef401ec8528be",
    "sum_20050414_132622_l1.tgz": "5ee7282404bfc03fa5584adb1c23f3d1f28ccb6e579eb3bf8c21ecf1aa92a5d7",
    "sum_20050415_153008_l1.tgz": "fb562861755f7df21a93d59a5a6bc6349017abd2bc41afa8796b1c4610ca6783",
    "sum_20050416_221213_l1.tgz": "269c29ac9d11ddc675facf8398141734016509048ca30089393ddf9d49f4d5fc",
    "sum_20050418_154813_l1.tgz": "34c53867bcaee6a24b6d800bfc60db58122e7190778e770073b0d56a8d95f8db",
    "sum_20050418_185319_l1.tgz": "98d11d3e044c7cf8827594346d58f847732a5f21df1ca29379a508d229bf6b14",
    "sum_20050517_080420_l1.tgz": "f753044a30dd9d9f5d00af09aaa013eb3808b48fe65896f2a1cd9ef8b625656f",
    "sum_20050518_080212_l1.tgz": "43fb80d0f9ed8c5202a7326427b451f5e04f18558b81d37e8d959181b06787ad",
    "sum_20050519_074609_l1.tgz": "79c91b91fe6c90dd67241aa1c835bc92db71ba1942822c4116de46826763a81d",
    "sum_20050520_080113_l1.tgz": "7d310c9e41e44fce29410c488bbae0c10ae22cc1d98403fae5687c3b6360d37a",
    "sum_20051007_090059_l1.tgz": "dec745328e720eafa33f582862dc987432cb7474b5a41e2c695295658df57b78",
    "sum_20051008_150112_l1.tgz": "947676cdaa92d1bd40e079e180a6b486d66e122b1c5857e1bf129daa867d5b58",
    "sum_20051009_090054_l1.tgz": "886e9f1bcf4484f1c19428ddb9e708100b2fb49706d79b3ed080f159325ee8b4",
    "sum_20051010_153012_l1.tgz": "1dc15b37091c6529048a251939c1d2b67a62a025e5ca2c0416d6326d835f4871",
    "sum_20051011_090319_l1.tgz": "ac4a67f6012cf64943cadac709d92634f29f2227d078596108de7d54687cff68",
    "sum_20051011_150101_l1.tgz": "602adc5097b7a53261301c366f8c371e54ed986b4ec72b4e2db90090932bab6b",
    "sum_20051011_160007_l1.tgz": "52549a8b698d6ed92f7a423690253a2bd3d016c05944496e55107b46e76a979f",
    "sum_20051012_150405_l1.tgz": "f819a74ceb6ee79d076710eb87ee19f3ee5e1e4b2c7f990634efa1517e960b9c",
    "sum_20051013_090317_l1.tgz": "784b045e2766da194175a2bb0b6e90329eab0569d78a5393779c5d1ff08d5ad1",
    "sum_20051014_150314_l1.tgz": "603f8ea4198053e62f4b0aeca39cada17ec07f6339895346558fc5cba40178aa",
    "sum_20051015_081606_l1.tgz": "dd7abf669f8c8e7abb8d88a1cf43da66546373e282a9bceb05572f87f807cca8",
    "sum_20051015_150116_l1.tgz": "a32070ca75e997a4a5e174a8de8364efd6633d42d4291412c46e4f2b46d76f10",
    "sum_20051016_105957_l1.tgz": "98f10c28ee44cc05cc505960f30697335d924054b78e334cc75c57a76ab4ac39",
    "sum_20051016_150307_l1.tgz": "0a2d690eba2c477b83e5d7b23e28ee7bf44efb162a4977f9305950a0edf26dd4",
    "sum_20051016_183703_l1.tgz": "b68bee2a19441c573dc67c83e898289ef405a9a08afc603248206c273e07901b",
    "sum_20070404_183708_l1.tgz": "e10deb9c50f7a919de8674423c6fd5d08d72392a894a36d3214fc0bc9cba6fc3",
    "sum_20070405_210427_l1.tgz": "60791237c9f54c38a8178a9bcd3953a6f4b7bc922d31016adc8bee20a1d016ac",
    "sum_20070406_210425_l1.tgz": "354ceea7beb23c36d7075ded2b872e2285d04205ffb799b1c9d2c128da019da9",
    "sum_20070410_170103_l1.tgz": "9b8254c8b324631fd6060c809f1f72879eb19901d54b4265c191821367337baa",
    "sum_20070410_200002_l1.tgz": "4b17051f45eecdcd6827d22ce450b700cbb0f99fd8c75dffc5fa68dd7db390b5",
    "sum_20070411_110057_l1.tgz": "29c868fea820d6fcaad29466097799d684badf433c5cdb3f03698a82fd44c0cb",
    "sum_20070412_200527_l1.tgz": "ad8b2f4075723022893a610aa959593c1be5074a6eb9ced070b3dacb71a02d7b",
    "sum_20070413_110100_l1.tgz": "c7a0cc23d5544e5a78f782e56e38721722c69ba0bba84e8c1cde1f9ad8533ae7",
    "sum_20070413_130130_l1.tgz": "bb93589a0f8202a7dab41d6a939bc8ecf60b1f61e27fb420d222cd4dbdf1482a",
    "sum_20070413_150138_l1.tgz": "3705f6bec44011e4312347b25f05838b096bbd54fc0664606052441543d186e8",
    "sum_20070414_192427_l1.tgz": "3bfb865b8156ac27436ddc751131a861f0157a1be67638faf7965c2c0f5b8c76",
    "sum_20070419_203923_l1.tgz": "1342e6efae77b00a1c30da78636ae03c237f368f5ce61f19ecc603fe4096c1dd",
    "sum_20070420_180556_l1.tgz": "63721105b87a8b14308e4dc9832d8333414fc39597017f0b825bbb06288f09c0",
    "sum_20071104_090113_l1.tgz": "c797d81fca67f28b30467777cb2131e6a475aa379244c3e2239c500434e59ae9",
    "sum_20071104_110055_l1.tgz": "31661750980f87e5aceae4b297ff3cffffa7ed60bc6c99cdcc1d59b6bb950b5c",
    "sum_20071105_010122_l1.tgz": "7509bc20e812ac916b5987e3e5fe18b0ee3f70f2a6ab9467531b8fc3eb40d284",
    "sum_20071105_050140_l1.tgz": "cb583201dadc2364e4623d0aa2dacaacef289934e9b65847eb9ea4226dce07b1",
    "sum_20071107_010054_l1.tgz": "3fb59cd886a7af8f9eab461ca6114912efa5a56bd92b931d197ed02f814da9c6",
    "sum_20071107_050131_l1.tgz": "ab52824c974712563be25a20698230254ada96312059c9530776b471176c9631",
    "sum_20071108_050113_l1.tgz": "f1775d920020918fa3d96d40d975b660abb854099b199ba0da47cf0fede4a97c",
    "sum_20071109_021604_l1.tgz": "52f5a314e46679ca841005ad539b5ddda69849d6a38dafd7b764b4dc8a311ed7",
    "sum_20071109_070127_l1.tgz": "6e58efaacf88791bb77354f55e21b1c0dcc880c7462064479c50b1d2c2b72619",
    "sum_20071109_110139_l1.tgz": "e543cf054c6a45894a4aad005b84f5424df23caeb6d949a9d5cee2250fd7c0eb",
    "sum_20071110_150108_l1.tgz": "3f8a2da50f6c5442ecf591d77bb447af2b892abe99402f09cd1c1615fd3b1e59",
    "sum_20071110_170056_l1.tgz": "3ea81f9d018a882cd931402adf0576834a95812d9654273d5178eb4a23bb1cb0",
    "sum_20071111_045709_l1.tgz": "53eb37efb9927d40aec043a9a211a217bce9e09f6608b359abb4c05884d45ebf",
    "sum_20071112_013516_l1.tgz": "3be2c395ec91a75383ea6b602b0072a328b1cdfd378e609a86c3d8d39751aea6",
    "sum_20071112_053430_l1.tgz": "2dbe28e647186b9a9df02d4e9a9fc95190f13c025654116baea00acf3be630bc",
    "sum_20071112_073255_l1.tgz": "3574492571a72be6f5537ff87a2cff684b423d0799ceb28134e22ee17bcc140e",
    "sum_20071113_030153_l1.tgz": "bc94f1980235784247745d02c233c32404194169b7b046cc353ef8e7e04cf3bb",
    "sum_20071114_010118_l1.tgz": "992ef074aeba1f5bbc6e13edd9c76848a3900e4cdcc8f269bdfd1112c233b74a",
    "sum_20071114_025833_l1.tgz": "3bff1120c667a8c00e5e20da81f8de02b47e35af552cbc04425997389fdb36d6",
    "sum_20071114_070141_l1.tgz": "0fd4401ef2e1a155a39fd701b8b999eea0ab28d0860c4d0cf47ce043fe19822c",
    "sum_20071114_122607_l1.tgz": "25a2cf801fd14bc2dfd16211d74d3cd0d47e87d61471dfaffc781071e9a25558",
    "sum_20071114_171047_l1.tgz": "6ef94a8f5ed19eba561b3d9a7604d20acb5cb75f4532852a700b35a7942186e6",
    "sum_20071114_210951_l1.tgz": "088f325e5cb043918153214ee9d926623a8555ab008da80c0af754ab4cbd922b",
    "sum_20071114_230716_l1.tgz": "b3ae3b4535f1d5e3f6c7acb4924a29149eb7ccd02a6a5fe90ac7049f6e185995",
    "sum_20071115_070255_l1.tgz": "5a4da6485a2c5c1a60ba0acd8c456734321457e0d563a9fd1ec419006d5ed452",
    "sum_20071116_180113_l1.tgz": "30ee3a57d7ba28d4ad83333b8ddde50e4e9ba0f95d94786fc94af0efe6b67d7d",
    "sum_20071116_221510_l1.tgz": "3b3bfc9206e1dc61de8656bb0ad62b4f63eb5e2db31c8f53743c6a95579894f6",
    "sum_20090417_120101_l1.tgz": "e2307357355a7a881158d2840b15710f18f73d92c712e29cb6b9be75c6e97cae",
    "sum_20090424_045503_l1.tgz": "84e0146e9dfb8d178282d519809cf891fe62622f8da1882b92e879097ee31530",
    "sum_20090424_065812_l1.tgz": "1ecafbe9f9cd5306255a45a4601d214049f89fe2ef44fc22317f08b5795f9aa8",
    "sum_20090428_140108_l1.tgz": "77e17472219fb69e0070c95096fdc445da4190756f34f12764da58cec5ff44de",
    "sum_20090428_160003_l1.tgz": "15dda3ccc43f966190b17d96ace8559616a1e4f797916f34504474eeabeba727",
    "sum_20090428_175902_l1.tgz": "398bc12aa0b901061ce6a43720c488a3d81e3400194784ec82f11a9e2496aa1d",
    "sum_20090428_200148_l1.tgz": "7c5b6c4049e3274cded68dfd967ddbfdac427ce14c0bea077dde921442f9eb89",
    "sum_20090429_000141_l1.tgz": "f1854a9ae8c1f861fc31f0cfbb16ec268de049151144a88f313e451c7a0d6be6",
    "sum_20090429_020039_l1.tgz": "f4f59ad676472226121d832b9b0dd4af7bbff746de5fe6197e5838d0071539bc",
}
"""The level-1 files of the archive, and the SHA-256 checksum of each."""


def url(name: str) -> str:
    """Where the SOHO archive serves a file."""
    return f"{url_archive}/{name[4:8]}/{name}"


def query(names: list[str]) -> dict[str, dict[str, str]]:
    """
    Ask ESA's catalogue of SOHO for the observation of each of the files, and
    its size, keyed by the name of the file.
    """
    listed = ", ".join(f"'{n}'" for n in names)
    adql = (
        f"SELECT {', '.join(f'{t}.{c}' for c, t in columns.items())} "
        "FROM soho.observation AS o "
        "JOIN soho.sumer_observation AS s ON o.observation_oid = s.observation_oid "
        f"WHERE o.file_name IN ({listed})"
    )
    data = urllib.parse.urlencode(
        {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql}
    ).encode()
    with urllib.request.urlopen(url_tap, data=data, timeout=300) as response:
        text = response.read().decode()
    rows = {}
    for row in csv.DictReader(text.splitlines()):
        if row["file_name"] in rows:
            raise ValueError(f"the catalogue lists {row['file_name']} twice")
        rows[row["file_name"]] = row
    missing = sorted(set(names) - set(rows))
    if missing:
        raise ValueError(f"the catalogue does not list {missing}")
    return rows


def download(url: str, path: pathlib.Path) -> None:
    """
    Download one file, trying again if the server fails.

    A download is written under another name until it is whole, so an
    interrupted one is never taken for the file.
    """
    path_partial = path.with_name(path.name + ".part")
    for attempt in range(10):
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                size = int(response.headers["Content-Length"])
                with open(path_partial, "wb") as f:
                    shutil.copyfileobj(response, f)
            if path_partial.stat().st_size != size:
                raise OSError(f"got {path_partial.stat().st_size} of {size} bytes")
            path_partial.replace(path)
            return
        except (urllib.error.URLError, OSError) as e:
            print(f"    {e}, trying again", flush=True)
            time.sleep(min(2**attempt, 300))
    raise RuntimeError(f"could not download {url}")


def copy(source: pathlib.Path, path: pathlib.Path) -> None:
    """Copy one file, under another name until it is whole."""
    path_partial = path.with_name(path.name + ".part")
    shutil.copyfile(source, path_partial)
    path_partial.replace(path)


def sha256(path: pathlib.Path) -> str:
    """The SHA-256 checksum of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def read_through(path: pathlib.Path) -> int:
    """
    Read every file in a gzipped tar archive, which checks the archive against
    the checksum gzip keeps of it, and return how many files it holds.
    """
    count = 0
    with tarfile.open(path, "r:gz") as tar:
        for member in tar:
            content = tar.extractfile(member)
            if content is not None:
                content.read()
                count += 1
    return count


def check(name: str, path: pathlib.Path, row: dict[str, str]) -> None:
    """
    Check a file against its checksum and its size in the catalogue, and
    check that it can be read through.
    """
    size = path.stat().st_size
    if size != int(row["file_size"]):
        raise ValueError(f"{name}: {size} bytes, not {row['file_size']}")
    if sha256(path) != files[name]:
        raise ValueError(f"{name}: the checksum differs")
    if read_through(path) == 0:
        raise ValueError(f"{name}: holds no files")


def build(directory: pathlib.Path, source: None | pathlib.Path = None) -> None:
    """
    Gather the files into `directory`, from `source` where they are there,
    check them, and write the manifest beside them.
    """
    directory.mkdir(parents=True, exist_ok=True)
    names = sorted(files)
    rows = query(names)
    print(f"{len(names)} files", flush=True)

    for name in names:
        path = directory / name
        if not path.exists():
            print(f"  {name}", flush=True)
            if source is not None and (source / name).exists():
                copy(source / name, path)
            else:
                download(url(name), path)
        check(name, path, rows[name])

    with open(directory / name_manifest, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("file", "url", "size", "sha256") + keys)
        for name in names:
            path = directory / name
            writer.writerow(
                (name, url(name), path.stat().st_size, files[name])
                + tuple(rows[name][k] for k in keys)
            )


if __name__ == "__main__":
    build(
        directory=pathlib.Path(sys.argv[1]),
        source=pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None,
    )
    print(pathlib.Path(sys.argv[1]) / name_manifest)

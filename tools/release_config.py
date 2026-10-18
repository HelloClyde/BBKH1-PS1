"""Public, unrestricted 408 MHz configuration used by local builds and CI."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OPTIONS=['--optimize','O3','--lto','--gpulib','--gpu-skip','1','--idle','--fast-spans',
         '--mxu','--video-hle','--vlc-hle','--fast-lsu','--fast-present','--mxu-rows',
         '--vlc-batch','--fast-spu','--audio-turbo','--cpu-mhz','408']
VARIANT='jit-o3-lto-gpulib-gskip1-idle-spans-mxu-vhle-vlc-spufast-lsu-present-mrows-vbatch-aturbo-cpu408'
BUILD=ROOT/'build'/VARIANT

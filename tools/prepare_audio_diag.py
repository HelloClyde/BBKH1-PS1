"""Instrument build copies only; normal audio/disc source bytes stay intact."""
from prepare import replace

def prepare_audio_diag(root,build):
    audio=build/'audio-diag-output.c';disc=build/'audio-diag-disc.cpp'
    audio.write_bytes((root/'src/audio.c').read_bytes());disc.write_bytes((root/'src/disc.cpp').read_bytes())
    replace(audio,'#include "spu_profile.h"','#include "spu_profile.h"\n#include "audio_diag.h"')
    replace(audio,'    initialized = batches = submitted = dropped = failures = nonzero = underruns = 0;',
                  '    initialized = batches = submitted = dropped = failures = nonzero = underruns = 0;\n    h1_audio_diag_reset();')
    replace(audio,'    if (consumed > queued) {',
                  '    h1_audio_diag_retire(consumed,queued,read_position,position);\n    if (consumed > queued) {')
    replace(audio,'++underruns; reset_ring(); finish_gap();return;',
                  '++underruns; reset_ring(); h1_audio_diag_gap_finish(); finish_gap();return;')
    replace(disc,'#include "h1_port.h"','#include "h1_port.h"\n#include "audio_diag.h"')
    replace(disc,'++h1_ps1_stats.disc_reads;h1_ps1_stats.disc_ticks+=h1_raw_tick_80hz()-tick;',
                  '++h1_ps1_stats.disc_reads;unsigned elapsed=h1_raw_tick_80hz()-tick;'
                  'h1_ps1_stats.disc_ticks+=elapsed;h1_audio_diag_io(lba,elapsed);')
    return audio,disc

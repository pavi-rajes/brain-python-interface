#include "plexfile.h"
#include "plexread.h"

const char names[][128] = {
    "spikes",
    "events",
    "wideband",
    "spkc",
    "lfp",
    "analog"
};

void plx_summary(PlexFile* plxfile) {
    int i;
    printf("Plexon file %s\n", plxfile->filename);
    for (i = 0; i < ChanType_MAX; i++) {
        printf("\t%8s: %lu / %lu\n", names[i], plxfile->data[i].num, plxfile->data[i].lim);
    }
}

void plx_print_frame(DataFrame* frame) {
    printf("%s at ts=%llu, fpos=[%lu, %lu], samples=%lu, len=%lu\n", 
            names[frame->type],
            frame->ts, frame->fpos[0], frame->fpos[1],
            frame->samples, frame->nblocks
            );
}

void plx_print_frameset(FrameSet* frameset, int num) {
    int i;
    for (i = 0; i < max(0, min(num, frameset->num)); i++) {
        plx_print_frame(&(frameset->frames[i]));
    }
}

int plx_check_frames(PlexFile* plxfile, ChanType type) {
    unsigned int i, invalid = 0;
    double tsdiff = 0;
    DataFrame* frame;
    FrameSet* frameset = &(plxfile->data[type]);
    double adfreq = (double) plxfile->header.ADFrequency;
    double freq;

    switch(type) {
        case wideband: case spkc: case lfp: case analog:
            freq = (double) plxfile->cont_info[type - wideband]->ADFreq;
            break;
        default:
            return -1;
    }

    if (frameset->num > 0) {
        for (i = 0; i < frameset->num-1; i++) {
            frame = &(frameset->frames[i]);
            tsdiff = (frameset->frames[i+1].ts - frame->ts) / adfreq;
            assert(tsdiff > 0);
            if ((frame->samples /(double) freq) != tsdiff) {
                printf("Found invalid frame, ts=%f, next=%f, diff=%f, samples=%lu, expect=%f\n", 
                    frame->ts / (double) adfreq, frameset->frames[i+1].ts / adfreq, tsdiff,
                    frame->samples, frame->samples / freq);
                invalid++;
            }
        }
    }
    return invalid;
}


int main(int argc, char** argv) {
    if (argc <= 1) {
        printf("Please supply a filename!\n");
        exit(1);
    }
    int i, bad;
    PlexFile* plxfile = plx_open(argv[1]);
    plx_summary(plxfile);
    plx_print_frameset(&(plxfile->data[analog]), 100);
    plx_print_frameset(&(plxfile->data[wideband]), 10);
    for (i = 0; i < ChanType_MAX; i++) {
        printf("Checking %s...\n", names[i]);
        fflush(stdout);
        bad = plx_check_frames(plxfile, i);
        printf("Found %d bad frames!\n", bad);
    }

    plx_check_frames(plxfile, lfp);

    FILE* fp = fopen(argv[2], "wb");
    
    int chans[5] = {0, 145, 146, 147, 161};
    ContInfo* info = plx_get_continuous(plxfile, analog, atof(argv[3]), atof(argv[4]), chans, 5);
    printf("Writing all analog data, shape (%lu, %lu), t_start=%f\n", info->len, info->nchans, info->t_start);
    double data[info->len*info->nchans];
    plx_read_continuous(info, data);
    fwrite(data, sizeof(double), info->nchans*info->len, fp);

    /*
    SpikeInfo* info = plx_get_discrete(plxfile, spike, atof(argv[3]), atof(argv[4]));
    Spike spikes[info->num];
    plx_read_discrete(info, spikes);
    
    fwrite(spikes, sizeof(Spike), info->num, fp);
    printf("Wrote out %d rows of spike data\n", info->num);
    */
    plx_close(plxfile);

    return 0;
}

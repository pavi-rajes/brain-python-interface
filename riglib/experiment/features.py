import time
import tempfile
import random
import traceback
import numpy as np

import pygame

from riglib import calibrations, bmi

from . import traits

class RewardSystem(traits.HasTraits):
    '''Use the reward system during the reward phase'''
    def __init__(self, *args, **kwargs):
        from riglib import reward
        super(RewardSystem, self).__init__(*args, **kwargs)
        self.reward = reward.open()

    def _start_reward(self):
        if self.reward is not None:
            self.reward.reward(self.reward_time*1000.)
        super(RewardSystem, self)._start_reward()

class Autostart(traits.HasTraits):
    '''Automatically begins the trial from the wait state, with a random interval drawn from `rand_start`'''
    rand_start = traits.Tuple((0.5, 2.), desc="Start interval")

    def __init__(self, *args, **kwargs):
        self.pause = False
        super(Autostart, self).__init__(*args, **kwargs)

    def _start_wait(self):
        s, e = self.rand_start
        self.wait_time = random.random()*(e-s) + s
        super(Autostart, self)._start_wait()
        
    def _test_start_trial(self, ts):
        return ts > self.wait_time and not self.pause
    
    def _test_premature(self, ts):
        return self.event is not None

class Button(object):
    '''Adds the ability to respond to the button, as well as to keyboard responses'''
    def screen_init(self):
        super(Button, self).screen_init()
        pygame.event.set_grab(True)
        pygame.mouse.set_visible(False)

    def _get_event(self):
        btnmap = {1:1, 3:4}
        for btn in pygame.event.get(pygame.MOUSEBUTTONDOWN):
            if btn.button in btnmap:
                return btnmap[btn.button]

        return super(Button, self)._get_event()
    
    def _while_reward(self):
        super(Button, self)._while_reward()
        pygame.event.clear()
    
    def _while_penalty(self):
        #Clear out the button buffers
        super(Button, self)._while_penalty()
        pygame.event.clear()
    
    def _while_wait(self):
        super(Button, self)._while_wait()
        pygame.event.clear()

class IgnoreCorrectness(object):
    '''Allows any response to be correct, not just the one defined. Overrides for trialtypes'''
    def __init__(self, *args, **kwargs):
        super(IgnoreCorrectness, self).__init__(*args, **kwargs)
        if hasattr(self, "trial_types"):
            for ttype in self.trial_types:
                del self.status[ttype]["%s_correct"%ttype]
                del self.status[ttype]["%s_incorrect"%ttype]
                self.status[ttype]["correct"] = "reward"
                self.status[ttype]["incorrect"] = "penalty"

    def _test_correct(self, ts):
        return self.event is not None

    def _test_incorrect(self, ts):
        return False


class AdaptiveGenerator(object):
    def __init__(self, *args, **kwargs):
        super(AdaptiveGenerator, self).__init__(*args, **kwargs)
        assert hasattr(self.gen, "correct"), "Must use adaptive generator!"

    def _start_reward(self):
        self.gen.correct()
        super(AdaptiveGenerator, self)._start_reward()
    
    def _start_incorrect(self):
        self.gen.incorrect()
        super(AdaptiveGenerator, self)._start_incorrect()






########################################################################################################
# Eyetracker datasources
########################################################################################################
class EyeData(traits.HasTraits):
    '''Pulls data from the eyetracking system and make it available on self.eyedata'''

    def init(self):
        from riglib import source
        src, ekw = self.eye_source
        self.eyedata = source.DataSource(src, **ekw)
        super(EyeData, self).init()
    
    @property
    def eye_source(self):
        from riglib import eyetracker
        return eyetracker.System, dict()

    def run(self):
        self.eyedata.start()
        try:
            super(EyeData, self).run()
        finally:
            self.eyedata.stop()
    
    def join(self):
        self.eyedata.join()
        super(EyeData, self).join()
    
    def _start_None(self):
        self.eyedata.pause()
        self.eyefile = tempfile.mktemp()
        print "retrieving data from eyetracker..."
        self.eyedata.retrieve(self.eyefile)
        print "Done!"
        self.eyedata.stop()
        super(EyeData, self)._start_None()
    
    def set_state(self, state, **kwargs):
        self.eyedata.sendMsg(state)
        super(EyeData, self).set_state(state, **kwargs)

    def cleanup(self, database, saveid, **kwargs):
        super(EyeData, self).cleanup(database, saveid, **kwargs)
        database.save_data(self.eyefile, "eyetracker", saveid)

class SimulatedEyeData(EyeData):
    '''Simulate an eyetracking system using a series of fixations, with saccades interpolated'''
    fixations = traits.Array(value=[(0,0), (-0.6,0.3), (0.6,0.3)], desc="Location of fixation points")
    fixation_len = traits.Float(0.5, desc="Length of a fixation")

    @property
    def eye_source(self):
        from riglib import eyetracker
        return eyetracker.Simulate, dict(fixations=fixations, fixation_len=fixation_len)

class CalibratedEyeData(EyeData):
    '''Filters eyetracking data with a calibration profile'''
    cal_profile = traits.Instance(calibrations.EyeProfile)

    def __init__(self, *args, **kwargs):
        super(CalibratedEyeData, self).__init__(*args, **kwargs)
        self.eyedata.set_filter(self.cal_profile)

class FixationStart(CalibratedEyeData):
    '''Triggers the start_trial event whenever fixation exceeds *fixation_length*'''
    fixation_length = traits.Float(2., desc="Length of fixation required to start the task")
    fixation_dist = traits.Float(50., desc="Distance from center that is considered a broken fixation")

    def __init__(self, *args, **kwargs):
        super(FixationStart, self).__init__(*args, **kwargs)
        self.status['wait']['fixation_break'] = "wait"
        self.log_exclude.add(("wait", "fixation_break"))
    
    def _start_wait(self):
        self.eyedata.get()
        super(FixationStart, self)._start_wait()

    def _test_fixation_break(self, ts):
        return (np.sqrt((self.eyedata.get()**2).sum(1)) > self.fixation_dist).any()
    
    def _test_start_trial(self, ts):
        return ts > self.fixation_length



########################################################################################################
# Phasespace datasources
########################################################################################################
class MotionData(traits.HasTraits):
    '''Enable reading of raw motiontracker data from Phasespace system'''
    marker_count = traits.Int(8, desc="Number of markers to return")

    def init(self):
        from riglib import source
        src, mkw = self.motion_source
        self.motiondata = source.DataSource(src, **mkw)
        super(MotionData, self).init()
    
    @property
    def motion_source(self):
        from riglib import motiontracker
        return motiontracker.make(self.marker_count), dict()

    def run(self):
        self.motiondata.start()
        try:
            super(MotionData, self).run()
        finally:
            self.motiondata.stop()
    
    def join(self):
        self.motiondata.join()
        super(MotionData, self).join()
    
    def _start_None(self):
        self.motiondata.stop()
        super(MotionData, self)._start_None()

class MotionSimulate(MotionData):
    '''Simulate presence of raw motiontracking system using a randomized spatial function'''
   
    @property
    def motion_source(self):
        from riglib import motiontracker
        cls = motiontracker.make(self.marker_count, cls=motiontracker.Simulate)
        return cls, dict(radius=(100,100,50), offset=(-150,0,0))

class MotionAutoAlign(MotionData):
    '''Creates an auto-aligning motion tracker, for use with the 6-point alignment system'''
    autoalign = traits.Instance(calibrations.AutoAlign)
    
    def init(self):
        super(MotionAutoAlign, self).init()
        self.motiondata.filter = self.autoalign

    @property
    def motion_source(self):
        from riglib import motiontracker
        cls = motiontracker.make(self.marker_count, cls=motiontracker.AligningSystem)
        return cls, dict()

########################################################################################################
# Plexon datasources
########################################################################################################
class SpikeData(traits.HasTraits):
    '''Stream neural spike data from the Plexon system'''
    plexon_channels = None
    
    def init(self):
        from riglib import plexon, source
        self.neurondata = source.DataSource(plexon.Spikes, channels=self.plexon_channels)
        super(SpikeData, self).init()

    def run(self):
        self.neurondata.start()
        try:
            super(SpikeData, self).run()
        finally:
            self.neurondata.stop()

class SpikeSimulate(object):
    pass

class SpikeBMI(SpikeData):
    '''Filters spike data through a BMI'''
    bmi = traits.Instance(bmi.BMI)

    def init(self):
        self.plexon_channels = self.bmi.units[:,0]
        try:
            self.dtype.append(('bins','u4',(len(self.bmi.units,))))
        except:
            pass

        print "init bmi"
        self.decoder = self.bmi
        super(SpikeBMI, self).init()
        #self.neurondata.filter = self.bmi


#*******************************************************************************************************
# Data Sinks
#*******************************************************************************************************
class SinkRegister(object):
    '''Superclass for all features which contain data sinks -- registers the various sources'''
    def init(self):
        from riglib import sink
        self.sinks = sink.sinks

        super(SinkRegister, self).init()

        if isinstance(self, (MotionData, MotionSimulate)):
            self.sinks.register(self.motiondata)
        if isinstance(self, (EyeData, CalibratedEyeData, SimulatedEyeData)):
            self.sinks.register(self.eyedata)

class SaveHDF(SinkRegister):
    '''Saves any associated MotionData and EyeData into an HDF5 file.'''
    def init(self):
        import tempfile
        from riglib import sink
        self.h5file = tempfile.NamedTemporaryFile()
        self.hdf = sink.sinks.start(self.hdf_class, filename=self.h5file.name)
        super(SaveHDF, self).init()

        try:
            self.dtype = np.dtype(self.dtype)
            self.hdf.register("task", self.dtype)
            self.task_data = np.zeros((1,), dtype=self.dtype)
        except:
            self.task_data = None

    @property
    def hdf_class(self):
        from riglib import hdfwriter
        return hdfwriter.HDFWriter

    def run(self):
        try:
            super(SaveHDF, self).run()
        finally:
            self.hdf.stop()

    def _cycle(self):
        if self.task_data is not None:
            self.hdf.send("task", self.task_data)
    
    def join(self):
        self.hdf.join()
        super(SaveHDF, self).join()

    def set_state(self, condition, **kwargs):
        self.hdf.sendMsg(condition)
        super(SaveHDF, self).set_state(condition, **kwargs)

    def cleanup(self, database, saveid, **kwargs):
        super(SaveHDF, self).cleanup(database, saveid, **kwargs)
        print "#################%s"%self.h5file.name
        database.save_data(self.h5file.name, "hdf", saveid)

class RelayPlexon(SinkRegister):
    '''Sends the full data from eyetracking and motiontracking systems directly into Plexon'''
    def init(self):
        from riglib import sink
        self.nidaq = sink.sinks.start(self.ni_out)
        super(RelayPlexon, self).init()

    @property
    def ni_out(self):
        from riglib import nidaq
        return nidaq.SendAll

    @property
    def plexfile(self):
        '''Calculates the plexon file that's most likely associated with the current task'''
        import os, sys, glob, time
        if len(self.event_log) < 1:
            return None
        
        start = self.event_log[-1][2]
        files = "/storage/plexon/*.plx"
        files = sorted(glob.glob(files), key=lambda f: abs(os.stat(f).st_mtime - start))
        
        if len(files) > 0:
            tdiff = os.stat(files[0]).st_mtime - start
            if abs(tdiff) < 60:
                 return files[0]
    
    def run(self):
        try:
            super(RelayPlexon, self).run()
        finally:
            self.nidaq.stop()

    def set_state(self, condition, **kwargs):
        self.nidaq.sendMsg(condition)
        super(RelayPlexon, self).set_state(condition, **kwargs)

    def cleanup(self, database, saveid, **kwargs):
        super(RelayPlexon, self).cleanup(database, saveid, **kwargs)
        time.sleep(2)
        if self.plexfile is not None:
            database.save_data(self.plexfile, "plexon", saveid, True, False)
        
class RelayPlexByte(RelayPlexon):
    '''Relays a single byte (0-255) as a row checksum for when a data packet arrives'''
    def init(self):
        if not isinstance(self, SaveHDF):
            raise ValueError("RelayPlexByte feature only available with SaveHDF")
        super(RelayPlexByte, self).init()

    @property
    def ni_out(self):
        from riglib import nidaq
        return nidaq.SendRowByte


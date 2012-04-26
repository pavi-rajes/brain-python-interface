import os
import time
import inspect
import traceback
import multiprocessing as mp
from multiprocessing import sharedctypes as shm

import numpy as np

import datasink
from . import FuncProxy

class DataSource(mp.Process):
    slice_size = 2
    slice_shape = (2,)
    
    def __init__(self, source, bufferlen=10, **kwargs):
        super(DataSource, self).__init__()
        self.filter = None
        self.source = source
        self.source_kwargs = kwargs
        self.bufferlen = bufferlen
        self.max_size = bufferlen*self.update_freq
        
        self.lock = mp.Lock()
        self.idx = shm.RawValue('l', 0)
        self.data = shm.RawArray('d', self.max_size*self.slice_size)
        self.pipe, self._pipe = mp.Pipe()
        self.cmd_event = mp.Event()
        self.status = mp.Value('b', 1)
        self.stream = mp.Event()

        self.methods = set(n for n in dir(source) if inspect.ismethod(getattr(source, n)))

    def start(self, *args, **kwargs):
        self.sinks = datasink.sinks.sinks
        super(DataSource, self).start(*args, **kwargs)

    def run(self):
        system = self.source(**self.source_kwargs)
        system.start()
        streaming = True
        
        size = self.slice_size
        while self.status.value > 0:
            if self.cmd_event.is_set():
                cmd, args, kwargs = self._pipe.recv()
                self.lock.acquire()
                try:
                    if cmd == "getattr":
                        print "getting %s"%repr(args)
                        ret = getattr(system, args[0])
                    else:
                        ret = getattr(system, cmd)(*args, **kwargs)
                except Exception as e:
                    traceback.print_exc()
                    ret = e
                self.lock.release()
                self._pipe.send(ret)
                self.cmd_event.clear()

            if self.stream.is_set():
                self.stream.clear()
                streaming = not streaming
                if streaming:
                    self.idx.value = 0
                    system.start()
                else:
                    system.stop()
            
            if streaming:
                data = system.get()
                for s in self.sinks:
                    s.send(system.__class__, data)

                if data is not None:
                    try:
                        self.lock.acquire()
                        i = self.idx.value % self.max_size
                        self.data[i*size:(i+1)*size] = np.ravel(data)
                        self.idx.value += 1
                        self.lock.release()
                    except:
                        print repr(data)
            else:
                time.sleep(.001)

        print "ending data collection"
        system.stop()

    def get(self):
        self.lock.acquire()
        i = (self.idx.value % self.max_size) * self.slice_size
        if self.idx.value > self.max_size:
            data = self.data[i:]+self.data[:i]
        else:
            data = self.data[:i]
        self.idx.value = 0
        self.lock.release()
        try:
            data = np.array(data).reshape((-1,)+self.slice_shape)
        except:
            print "can't reshape, len(data)=%d, size[source]=%d"%(len(data), self.slice_size)

        if self.filter is not None:
            return self.filter(data)
        return data

    def pause(self):
        self.stream.set()

    def stop(self):
        self.status.value = -1
    
    def __del__(self):
        self.stop()

    def __getattr__(self, attr):
        if attr in self.methods:
            return FuncProxy(attr, self.pipe, self.cmd_event)
        else:
            self.pipe.send(("getattr", (attr,), {}))
            self.cmd_event.set()
            return self.pipe.recv()

class EyeData(DataSource):
    def __init__(self, **kwargs):
        from riglib import eyetracker
        self.update_freq = 500
        super(EyeData, self).__init__(eyetracker.System, **kwargs)

class EyeSimulate(DataSource):
    def __init__(self, **kwargs):
        from riglib import eyetracker
        self.update_freq = 500
        super(EyeSimulate, self).__init__(eyetracker.Simulate, **kwargs)

class MotionData(DataSource):
    def __init__(self, marker_count=8, **kwargs):
        from riglib import motiontracker
        self.slice_size = marker_count * 3
        self.slice_shape = (marker_count, 3)
        self.update_freq = 480
        super(MotionData, self).__init__(motiontracker.System, marker_count=marker_count, **kwargs)

class MotionSimulate(DataSource):
    def __init__(self, marker_count = 8, **kwargs):
        from riglib import motiontracker
        self.slice_size = marker_count * 3
        self.slice_shape = (marker_count, 3)
        self.update_freq = 480
        super(MotionSimulate, self).__init__(motiontracker.Simulate, marker_count=marker_count, **kwargs)

if __name__ == "__main__":
    sim = MotionData()
    sim.start()
    #sim.get()

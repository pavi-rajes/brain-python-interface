'''
Various types of "assist", i.e. different methods for shared control
between neural control and machine control. Only applies in cases where
some knowledge of the task goals is available. 
'''

import numpy as np 
from riglib.stereo_opengl import ik
from riglib.bmi import feedback_controllers
import pickle

class Assister(object):
    '''
    Parent class for various methods of assistive BMI. Children of this class 
    can compute an "optimal" input to the system, which is mixed in with the input
    derived from the subject's neural input. The parent exists primarily for 
    interface standardization and type-checking.
    '''
    def calc_assisted_BMI_state(self, current_state, target_state, assist_level, mode=None, **kwargs):
        '''
        Main assist calculation function

        Parameters
        ----------
        current_state: np.ndarray of shape (n_states, 1)
            Vector representing the current state of the prosthesis 
        target_state: np.ndarray of shape (n_states, 1)
            Vector representing the target state of the prosthesis, i.e. the optimal state for the prosthesis to be in
        assist_level: float
            Number indicating the level of the assist. This can in general have arbitrary units but most assisters
            will have this be a number in the range (0, 1) where 0 is no assist and 1 is full assist
        mode: hashable type, optional, default=None
            Indicator of which mode of the assistive controller to use. When applied, this 'mode' is used as a dictionary key and must be hashable

        Returns
        -------
        '''
        pass  # implement in subclasses -- should return (Bu, assist_weight)

    def __call__(self, *args, **kwargs):
        '''
        Wrapper for self.calc_assisted_BMI_state
        '''
        return self.calc_assisted_BMI_state(*args, **kwargs)


class OFCEndpointAssister(Assister):
    def __init__(self, decoding_rate=180):
        self.F_assist = pickle.load(open('/storage/assist_params/assist_20levels_ppf.pkl'))
        self.n_assist_levels = len(self.F_assist)                              
        self.prev_assist_level = self.n_assist_levels          
        self.B = np.mat(np.vstack([np.zeros([3,3]), np.eye(3)*1000*1./decoding_rate, np.zeros(3)]))

    def calc_assisted_BMI_state(self, current_state, target_state, assist_level, mode=None, **kwargs):
        ##assist_level_idx = min(int(assist_level * self.n_assist_levels), self.n_assist_levels-1)
        ##if assist_level_idx < self.prev_assist_level:                        
        ##    print "assist_level_idx decreasing to", assist_level_idx         
        ##    self.prev_assist_level = assist_level_idx                        
        ##F = np.mat(self.F_assist[assist_level_idx])    
        F = self.get_F(assist_level)
        Bu = self.B*F*(target_state - current_state)
        print Bu
        return Bu, 0

    def get_F(self, assist_level):
        assist_level_idx = min(int(assist_level * self.n_assist_levels), self.n_assist_levels-1)
        if assist_level_idx < self.prev_assist_level:                        
            print "assist_level_idx decreasing to", assist_level_idx         
            self.prev_assist_level = assist_level_idx                        
        F = np.mat(self.F_assist[assist_level_idx])    
        return F

class LinearFeedbackControllerAssist(Assister):
    '''
    Assister where the machine control is an LQR controller, possibly with different 'modes' depending on the state of the task
    '''
    def __init__(self, A, B, Q, R):
        '''
        Constructor for LinearFeedbackControllerAssist

        The system should evolve as
        $$x_{t+1} = Ax_t + Bu_t + w_t; w_t ~ N(0, W)$$

        with infinite horizon cost 
        $$\sum{t=0}^{+\infty} (x_t - x_target)^T * Q * (x_t - x_target) + u_t^T * R * u_t$$

        Parameters
        ----------
        A: np.ndarray of shape (n_states, n_states)
            Model of the state transition matrix of the system to be controlled. 
        B: np.ndarray of shape (n_states, n_controls)
            Control input matrix of the system to be controlled. 
        Q: np.ndarray of shape (n_states, n_states)
            Quadratic cost on state
        R: np.ndarray of shape (n_controls, n_controls)
            Quadratic cost on control inputs

        Returns
        -------
        LinearFeedbackControllerAssist instance
        '''
        self.lqr_controller = feedback_controllers.LQRController(A, B, Q, R)
        # self.A = A
        # self.B = B
        # self.F = feedback_controllers.LQRController.dlqr(A, B, Q, R)

    def calc_assisted_BMI_state(self, current_state, target_state, assist_level, mode=None, **kwargs):
        '''
        See docs for Assister.calc_assisted_BMI_state
        '''
        Bu = assist_level * self.lqr_controller(current_state, target_state)
        assist_weight = 0
        # assist_weight = assist_level
        # B = self.B
        # F = self.F
        # Bu = assist_level * B*F*(target_state - current_state)
        # assist_weight = assist_level
        return Bu, assist_weight

class SSMLFCAssister(LinearFeedbackControllerAssist):
    def __init__(self, ssm, Q, R, **kwargs):
        '''
        Constructor for TentacleAssist

        Parameters
        ----------
        ssm: riglib.bmi.state_space_models.StateSpace instance
            The state-space model's A and B matrices represent the system to be controlled
        args: positional arguments
            These are ignored (none are necessary)
        kwargs: keyword arguments
            The constructor must be supplied with the 'kin_chain' kwarg, which must have the attribute 'link_lengths'
            This is specific to 'KinematicChain' plants.

        Returns
        -------
        TentacleAssist instance

        '''        
        if ssm == None:
            raise ValueError("SSMLFCAssister requires a state space model!")

        A, B, W = ssm.get_ssm_matrices()
        super(SSMLFCAssister, self).__init__(A, B, Q, R)

class TentacleAssist(SSMLFCAssister):
    '''
    Assister which can be used for a kinematic chain of any length. The cost function is calibrated for the experiments with the 4-link arm
    '''
    def __init__(self, ssm, *args, **kwargs):
        '''
        Constructor for TentacleAssist

        Parameters
        ----------
        ssm: riglib.bmi.state_space_models.StateSpace instance
            The state-space model's A and B matrices represent the system to be controlled
        args: positional arguments
            These are ignored (none are necessary)
        kwargs: keyword arguments
            The constructor must be supplied with the 'kin_chain' kwarg, which must have the attribute 'link_lengths'
            This is specific to 'KinematicChain' plants.

        Returns
        -------
        TentacleAssist instance

        '''
        try:
            kin_chain = kwargs.pop('kin_chain')
        except KeyError:
            raise ValueError("kin_chain must be supplied for TentacleAssist")
        
        A, B, W = ssm.get_ssm_matrices()
        Q = np.mat(np.diag(np.hstack([kin_chain.link_lengths, np.zeros_like(kin_chain.link_lengths), 0])))
        R = 10000*np.mat(np.eye(B.shape[1]))

        super(TentacleAssist, self).__init__(ssm, Q, R)

    # def calc_assisted_BMI_state(self, *args, **kwargs):
    #     '''
    #     see Assister.calc_assisted_BMI_state. This method always returns an 'assist_weight' of 0, 
    #     which is required for the feedback controller style of assist to cooperate with the rest of the 
    #     Decoder
    #     '''
    #     Bu, _ = super(TentacleAssist, self).calc_assisted_BMI_state(*args, **kwargs)
    #     assist_weight = 0
    #     return Bu, assist_weight


class SimpleEndpointAssister(Assister):
    '''
    Constant velocity toward the target if the cursor is outside the target. If the
    cursor is inside the target, the speed becomes the distance to the center of the
    target divided by 2.
    '''
    def __init__(self, *args, **kwargs):
        '''    Docstring    '''
        self.decoder_binlen = kwargs.pop('decoder_binlen', 0.1)
        self.assist_speed = kwargs.pop('assist_speed', 5.)
        self.target_radius = kwargs.pop('target_radius', 2.)

    def calc_assisted_BMI_state(self, current_state, target_state, assist_level, mode=None, **kwargs):
        '''    Docstring    '''
        Bu = None
        assist_weight = 0.

        if assist_level > 0:
            cursor_pos = np.array(current_state[0:3,0]).ravel()
            target_pos = np.array(target_state[0:3,0]).ravel()
            decoder_binlen = self.decoder_binlen
            speed = self.assist_speed * decoder_binlen
            target_radius = self.target_radius
            Bu = endpoint_assist_simple(cursor_pos, target_pos, decoder_binlen, speed, target_radius, assist_level)
            assist_weight = assist_level 

        return Bu, assist_weight


class Joint5DOFEndpointTargetAssister(SimpleEndpointAssister):
    '''
    Assister for 5DOF 3-D arm (e.g., a kinematic model of the exoskeleton), restricted to movements in a 2D plane
    '''
    def __init__(self, arm, *args, **kwargs):
        '''    Docstring    '''
        self.arm = arm
        super(Joint5DOFEndpointTargetAssister, self).__init__(*args, **kwargs)

    def calc_assisted_BMI_state(self, current_state, target_state, assist_level, mode=None, **kwargs):
        '''    Docstring    '''
        Bu = None # By default, no assist
        assist_weight = 0.

        if assist_level> 0:
            cursor_joint_pos = np.asarray(current_state)[[1,3],0]
            cursor_pos       = self.arm.perform_fk(cursor_joint_pos)
            target_joint_pos = np.asarray(target_state)[[1,3],0]
            target_pos       = self.arm.perform_fk(target_joint_pos)

            arm              = self.arm
            decoder_binlen   = self.decoder_binlen
            speed            = self.assist_speed * decoder_binlen
            target_radius    = self.target_radius

            # Get the endpoint control under full assist
            # Note: the keyword argument "assist_level" is intended to be set to 1. (and not self.current_level) 
            Bu_endpoint = endpoint_assist_simple(cursor_pos, target_pos, decoder_binlen, speed, target_radius, assist_level=1.)

            # Convert the endpoint assist to joint space using IK/Jacobian
            Bu_endpoint = np.array(Bu_endpoint).ravel()
            endpt_pos = Bu_endpoint[0:3]
            endpt_vel = Bu_endpoint[3:6]

            l_upperarm, l_forearm = arm.link_lengths
            shoulder_center = np.array([0., 0., 0.])#arm.xfm.move
            joint_pos, joint_vel = ik.inv_kin_2D(endpt_pos - shoulder_center, l_upperarm, l_forearm, vel=endpt_vel)

            Bu_joint = np.hstack([joint_pos[0].view((np.float64, 5)), joint_vel[0].view((np.float64, 5)), 1]).reshape(-1, 1)

            # Downweight the joint assist
            Bu = assist_level * np.mat(Bu_joint).reshape(-1,1)
            assist_weight = assist_level

        return Bu, assist_weight


def endpoint_assist_simple(cursor_pos, target_pos, decoder_binlen=0.1, speed=0.5, target_radius=2., assist_level=0.):
    '''    Docstring    '''
    diff_vec = target_pos - cursor_pos 
    dist_to_target = np.linalg.norm(diff_vec)
    dir_to_target = diff_vec / (np.spacing(1) + dist_to_target)
    
    if dist_to_target > target_radius:
        assist_cursor_pos = cursor_pos + speed*dir_to_target
    else:
        assist_cursor_pos = cursor_pos + speed*diff_vec/2

    assist_cursor_vel = (assist_cursor_pos-cursor_pos)/decoder_binlen
    Bu = assist_level * np.hstack([assist_cursor_pos, assist_cursor_vel, 1])
    Bu = np.mat(Bu.reshape(-1,1))
    return Bu


class SimpleEndpointAssisterLFC(feedback_controllers.MultiModalLFC):
    def __init__(self, *args, **kwargs):        
        dt = 0.1
        A = np.mat([[1., 0, 0, dt, 0, 0, 0], 
                    [0., 1, 0, 0,  dt, 0, 0],
                    [0., 0, 1, 0, 0, dt, 0],
                    [0., 0, 0, 0, 0,  0, 0],
                    [0., 0, 0, 0, 0,  0, 0],
                    [0., 0, 0, 0, 0,  0, 0],
                    [0., 0, 0, 0, 0,  0, 1]])


        I = np.mat(np.eye(3))
        B = np.vstack([0*I, I, np.zeros([1,3])])
        F_target = np.hstack([I, 0*I, np.zeros([3,1])])
        F_hold = np.hstack([0*I, 0*I, np.zeros([3,1])])
        F_dict = dict(hold=F_hold, target=F_target)
        super(SimpleEndpointAssisterLFC, self).__init__(B=B, F=F_dict)

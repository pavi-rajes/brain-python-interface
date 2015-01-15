'''
Classes for BMI decoding using the Point-process filter. 
'''

import numpy as np

import bmi
from bmi import GaussianState
import statsmodels.api as sm
from scipy.io import loadmat
import time
import cmath
import feedback_controllers
import pickle
import train

class PointProcessFilter(bmi.GaussianStateHMM):
    """
    Low-level Point-process filter, agnostic to application

    Model: 
       x_{t+1} = Ax_t + Bu_t + w_t; w_t ~ N(0, W)
       log(y_t) = Cx_t
    """
    model_attrs = ['A', 'W', 'C']

    def __init__(self, A=None, W=None, C=None, dt=None, is_stochastic=None, B=0, F=0):
        '''
        Constructor for PointProcessFilter

        Parameters
        ----------
        A : np.mat
            Model of state transition matrix
        W : np.mat
            Model of process noise covariance
        C : np.mat
            Model of conditional distribution between observations and hidden state
            log(obs) = C * hidden_state
        dt : float
            Discrete-time sampling rate of the filter. Used to map spike counts to spike rates
        B : np.ndarray, optional
            Control input matrix
        F : np.ndarray, optional
            State-space feedback gain matrix to drive state back to equilibrium state.
        is_stochastic : np.array, optional
            Array of booleans specifying for each state whether it is stochastic. 
            If 'None' specified, all states are assumed to be stochastic

        Returns
        -------
        KalmanFilter instance
        '''
        if A is None and W is None and C is None and dt is None:
            ## This condition should only be true in the unpickling phase
            pass            
        else:
            self.A = np.mat(A)
            self.W = np.mat(W)
            self.C = np.mat(C)
            self.dt = dt
            self.spike_rate_dt = dt
            
            self.B = B
            self.F = F

            if is_stochastic == None:
                n_states = A.shape[0]
                self.is_stochastic = np.ones(n_states, dtype=bool)
            else:
                self.is_stochastic = np.array(is_stochastic)
            
            self.state_noise = GaussianState(0.0, W)
            self._pickle_init()

    def _pickle_init(self):
        """
        Code common to unpickling and initialization
        """
        nS = self.A.shape[0]
        offset_row = np.zeros(nS)
        offset_row[-1] = 1
        self.include_offset = np.array_equal(np.array(self.A)[-1, :], offset_row)

        self.spike_rate_dt = self.dt

        if not hasattr(self, 'B'): self.B = 0
        if not hasattr(self, 'F'): self.F = 0

    def _init_state(self, init_state=None, init_cov=None):
        """
        Initialize the state of the KF prior to running in real-time

        Parameters
        ----------
        
        Returns
        -------

        """
        ## Initialize the BMI state, assuming 
        nS = self.A.shape[0] # number of state variables
        if init_state == None:
            init_state = np.mat( np.zeros([nS, 1]) )
            if self.include_offset: init_state[-1,0] = 1
        if init_cov == None:
            init_cov = np.mat( np.zeros([nS, nS]) )
        self.state = GaussianState(init_state, init_cov) 
        self.state_noise = GaussianState(0.0, self.W)
        self.id = np.zeros([1, self.C.shape[0]])

    def _check_valid(self, lambda_predict):
        '''
        Docstring    
        
        Parameters
        ----------
        
        Returns
        -------
        '''
        if np.any((lambda_predict * self.spike_rate_dt) > 1): 
            raise ValueError("Cell exploded!")

    def _obs_prob(self, state):
        '''
        Docstring    
        
        Parameters
        ----------
        
        Returns
        -------
        '''
        Loglambda_predict = self.C * state.mean
        lambda_predict = np.exp(Loglambda_predict)/self.spike_rate_dt

        nan_inds = np.isnan(lambda_predict)
        lambda_predict[nan_inds] = 0

        # check max rate is less than 1 b/c it's a probability
        rate_too_high_inds = ((lambda_predict * self.spike_rate_dt) > 1)
        lambda_predict[rate_too_high_inds] = 1./self.spike_rate_dt

        # check min rate is > 0
        rate_too_low_inds = (lambda_predict < 0)
        lambda_predict[rate_too_low_inds] = 0

        invalid_inds = nan_inds | rate_too_high_inds | rate_too_low_inds
        if np.any(invalid_inds):
            pass
            #print np.nonzero(invalid_inds.ravel()[0])
        return lambda_predict
    
    def _ssm_pred(self, state, target_state=None):
        '''
        Docstring    
        
        Parameters
        ----------
        
        Returns
        -------
        '''
        A = self.A
        B = self.B
        F = self.F
        if target_state == None:
            return A*state + self.state_noise
        else:
            return (A - B*F)*state + B*F*target_state + self.state_noise

    def _forward_infer(self, st, obs_t, x_target=None, **kwargs):
        '''
        Docstring    
        
        Parameters
        ----------
        
        Returns
        -------
        '''
        if x_target is not None:
            x_target = np.mat(x_target[:,0].reshape(-1,1))
        target_state = x_target

        obs_t = np.mat(obs_t.reshape(-1,1))
        C = self.C
        n_obs, n_states = C.shape
        
        dt = self.spike_rate_dt
        inds, = np.nonzero(self.is_stochastic)
        mesh = np.ix_(inds, inds)
        A = self.A
        W = self.W
        C = C[:,inds]

        x_prev, P_prev = st.mean, st.cov
        B = self.B
        F = self.F
        if target_state == None or np.any(np.isnan(target_state)):
            x_pred = A*x_prev
            P_pred = A*P_prev*A.T + W
        else:
            x_pred = A*x_prev + B*F*(target_state - x_prev)
            P_pred = (A-B*F) * P_prev * (A-B*F).T + W
            if np.all(B*F == 0):
                #import pdb; pdb.set_trace()
                if not (np.array_equal(A*x_prev, A*x_prev + B*F*(target_state - x_prev)) and np.array_equal((A-B*F) * P_prev * (A-B*F).T + W, A*P_prev*A.T + W)):
                    print 'wtf'
        P_pred = P_pred[mesh]

        Loglambda_predict = self.C * x_pred 
        exp = np.vectorize(lambda x: np.real(cmath.exp(x)))
        lambda_predict = exp(np.array(Loglambda_predict).ravel())/dt

        Q_inv = np.mat(np.diag(lambda_predict*dt))

        if np.linalg.cond(P_pred) > 1e5:
            P_est = P_pred;
        else:
            P_est = (P_pred.I + C.T*np.mat(np.diag(lambda_predict*dt))*C).I

        # inflate P_est
        P_est_full = np.mat(np.zeros([n_states, n_states]))
        P_est_full[mesh] = P_est
        P_est = P_est_full 

        unpred_spikes = obs_t - np.mat(lambda_predict*dt).reshape(-1,1)

        x_est = np.mat(np.zeros([n_states, 1]))
        x_est = x_pred + P_est*self.C.T*unpred_spikes
        post_state = GaussianState(x_est, P_est)

        return post_state

    def __getstate__(self):
        '''
        Return model parameters to be pickled. Overrides the default __getstate__ so that things like the P matrix aren't pickled.
        
        Parameters
        ----------
        None
        
        Returns
        -------
        dict
        '''
        return dict(A=self.A, W=self.W, C=self.C, dt=self.dt, B=self.B, 
                    is_stochastic=self.is_stochastic, S=self.S)

    def tomlab(self, unit_scale=1.):
        '''
        Convert to the MATLAB beta matrix convention from the one used here (different state order, transposed)
        '''
        return np.array(np.hstack([self.C[:,-1], unit_scale*self.C[:,self.is_stochastic]])).T

    @classmethod
    def frommlab(self, beta_mat):
        '''
        Convert from the MATLAB beta matrix convention to the one used here (different state order, transposed)
        '''
        return np.vstack([beta_mat[1:,:], beta_mat[0,:]]).T

    @classmethod
    def MLE_obs_model(cls, hidden_state, obs, include_offset=True, drives_obs=None):
        """
        Unconstrained ML estimator of {C, } given observations and
        the corresponding hidden states
        Docstring    
        
        Parameters
        ----------
        
        Returns
        -------            
        """
        assert hidden_state.shape[1] == obs.shape[1]
    
        if isinstance(hidden_state, np.ma.core.MaskedArray):
            mask = ~hidden_state.mask[0,:] # NOTE THE INVERTER 
            inds = np.nonzero([ mask[k]*mask[k+1] for k in range(len(mask)-1)])[0]
    
            X = np.mat(hidden_state[:,mask])
            T = len(np.nonzero(mask)[0])
    
            Y = np.mat(obs[:,mask])
            if include_offset:
                X = np.vstack([ X, np.ones([1,T]) ])
        else:
            num_hidden_state, T = hidden_state.shape
            X = np.mat(hidden_state)
            if include_offset:
                X = np.vstack([ X, np.ones([1,T]) ])
                if not drives_obs == None:
                    drives_obs = np.hstack([drives_obs, True])
                
            Y = np.mat(obs)
        
        X = np.array(X)
        if not drives_obs == None:
            X = X[drives_obs, :]
        Y = np.array(Y)

        # ML estimate of C and Q
        n_units = Y.shape[0]
        n_states = X.shape[0]
        C = np.zeros([n_units, n_states])
        pvalues = np.zeros([n_units, n_states])
        glm_family = sm.families.Poisson()
        for k in range(n_units):
            model = sm.GLM(Y[k,:], X.T, family=glm_family)
            model_fit = model.fit()
            C[k,:] = model_fit.params
            pvalues[k,:] = model_fit.pvalues

        return C, pvalues

class PPFDecoder(bmi.BMI, bmi.Decoder):
    def _pickle_init(self):
        '''
        Docstring    
        
        Parameters
        ----------
        
        Returns
        -------
        '''
        ### # initialize the F_assist matrices
        ### # TODO this needs to be its own function...
        ### tau_scale = (28.*28)/1000/3. * np.array([18., 12., 6, 3., 2.5, 1.5])
        ### num_assist_levels = len(tau_scale)
        ### 
        ### w_x = 1;
        ### w_v = 3*tau_scale**2/2;
        ### w_r = 1e6*tau_scale**4;
        ### 
        ### I = np.eye(3)
        ### self.filt.B = np.bmat([[0*I], 
        ###               [self.filt.dt/1e-3 * I],
        ###               [np.zeros([1, 3])]])

        ### F = []
        ### F.append(np.zeros([3, 7]))
        ### for k in range(num_assist_levels):
        ###     Q = np.mat(np.diag([w_x, w_x, w_x, w_v[k], w_v[k], w_v[k], 0]))
        ###     R = np.mat(np.diag([w_r[k], w_r[k], w_r[k]]))

        ###     F_k = np.array(feedback_controllers.LQRController.dlqr(self.filt.A, self.filt.B, Q, R, eps=1e-15))
        ###     F.append(F_k)
        ### 
        ### self.F_assist = np.dstack([np.array(x) for x in F]).transpose([2,0,1])
        #if not hasattr(self, 'F_assist'):
        self.F_assist = pickle.load(open('/storage/assist_params/assist_20levels_ppf.pkl'))
        self.n_assist_levels = len(self.F_assist)
        self.prev_assist_level = self.n_assist_levels

        super(PPFDecoder, self)._pickle_init()

    def __call__(self, obs_t, **kwargs):
        '''
        Docstring    
        
        Parameters
        ----------
        
        Returns
        -------
        '''
        # The PPF model predicts that at most one spike can be observed in 
        # each bin; if more are observed, squash the counts
        obs_t = obs_t.copy()
        obs_t[obs_t > 1] = 1
        return super(PPFDecoder, self).__call__(obs_t, **kwargs)

    def shuffle(self):
        '''
        Shuffle the neural model
        
        Parameters
        ----------
        None
        
        Returns
        -------
        None
        '''
        import random
        inds = range(self.filt.C.shape[0])
        random.shuffle(inds)

        # shuffle rows of C
        self.filt.C = self.filt.C[inds, :]

    def compute_suff_stats(self, hidden_state, obs, include_offset=True):
        '''
        Calculate initial estimates of the parameter sufficient statistics used in the RML update rules

        Parameters
        ----------
        hidden_state : np.ndarray of shape (n_states, n_samples)
            Examples of the hidden state x_t taken from training seed data.  
        obs : np.ndarray of shape (n_features, n_samples)
            Multiple neural observations paired with each of the hidden state examples
        include_offset : bool, optional
            If true, a state of all 1's is added to the hidden_state to represent mean offsets. True by default

        Returns
        -------
        R : np.ndarray of shape (n_states, n_states)
            Proportional to covariance of the hidden state samples 
        S : np.ndarray of shape (n_features, n_states)
            Proportional to cross-covariance between 
        T : np.ndarray of shape (n_features, n_features)
            Proportional to covariance of the neural observations
        ESS : float
            Effective number of samples. In the initialization, this is just the 
            dimension of the array passed in, but the parameter can become non-integer 
            during the update procedure as old parameters are "forgotten".
        '''
        assert hidden_state.shape[1] == obs.shape[1]
    
        if isinstance(hidden_state, np.ma.core.MaskedArray):
            mask = ~hidden_state.mask[0,:] # NOTE THE INVERTER 
            inds = np.nonzero([ mask[k]*mask[k+1] for k in range(len(mask)-1)])[0]
    
            X = np.mat(hidden_state[:,mask])
            n_pts = len(np.nonzero(mask)[0])
    
            Y = np.mat(obs[:,mask])
            if include_offset:
                X = np.vstack([ X, np.ones([1,n_pts]) ])
        else:
            num_hidden_state, n_pts = hidden_state.shape
            X = np.mat(hidden_state)
            if include_offset:
                X = np.vstack([ X, np.ones([1,n_pts]) ])
            Y = np.mat(obs)
        X = np.mat(X, dtype=np.float64)

        C = self.filt.C
        dt = self.filt.dt

        S = np.zeros([Y.shape[0], X.shape[0]])
        n_samples = X.shape[1]
        for k in range(n_samples):
            x_t = X[:, k]
            Loglambda_predict = C[:,self.drives_neurons] * x_t
            exp = np.vectorize(lambda x: np.real(cmath.exp(x)))
            lambda_predict = exp(np.array(Loglambda_predict).ravel())/dt
            Q_inv = np.mat(np.diag(lambda_predict*dt))

            y_t = Y[:,k]
            S += Q_inv*y_t*x_t.T

        # R = (X * X.T)
        # S = (Y * X.T)
        # T = (Y * Y.T)
        # ESS = n_pts

        return (S,)

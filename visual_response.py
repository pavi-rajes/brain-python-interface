from riglib.experiment import consolerun
from riglib.tasks import Dots

if __name__ == "__main__":
    options = {
        "penalty_time": 5,
        "ignore_time": 4, 
        "rand_start": (1, 10), 
        "reward_time": 5, 
        "timeout_time": 3,
        "trial_probs": [0, None], 
    }
<<<<<<< HEAD
    exp = consolerun(Dots, ("autostart","button","ignore_correctness"), **options)
=======
    exp = consolerun(Dots, ("autostart","button","ignore_correctness"), **options)
>>>>>>> Adding trial reporting

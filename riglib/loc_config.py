import os
hostname = os.popen('hostname').readlines()[0].rstrip()

if hostname == 'arc':
    reward_system_version = 1
    display_start_pos = "1920,0"
    recording_system = "plexon"
elif hostname == 'nucleus':
    # Older Crist reward system (single channel)
    reward_system_version = 0
    display_start_pos = "0,0"
    recording_system = "plexon"
else:
    recording_system = "blackrock"

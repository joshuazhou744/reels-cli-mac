import subprocess
import time
from collections import deque
from threading import Thread
from instagram.instagram_client import InstagramClient
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
INITIAL_BUFFER = 3      # how many reels to load initially
MAX_FORWARD_BUFFER = 5  # keep at least this many reels ahead
MAX_BACKWARD_BUFFER = 2 # max reels to keep behind (dequeue older ones)
SOCKET = "/tmp/socket"

# Start mpv player via run.sh
def start_mpv():
    subprocess.Popen(["./run.sh", ""])  # run with empty first link
    time.sleep(1)  # wait for IPC socket to be ready


# Append a reel via q.sh
def append_reel(url: str):
    subprocess.run(["./q.sh", str(url)])


# Remove first reel via dq.sh
def remove_first_reel():
    subprocess.run(["./dq.sh"])


# Thread to maintain forward/backward buffer
def buffer_manager(video_queue: deque, client: InstagramClient):
    last_pk = 0
    while True:
        # Keep forward buffer filled
        while len(video_queue) < MAX_FORWARD_BUFFER:
            reels, last_pk = client.fetch_reels(last_pk=last_pk, count=5)
            for url in reels:
                append_reel(url)
                video_queue.append(url)
            time.sleep(0.5)  # small pause to avoid flooding IPC

        # Keep backward buffer within threshold
        while len(video_queue) > MAX_BACKWARD_BUFFER + MAX_FORWARD_BUFFER:
            remove_first_reel()
            video_queue.popleft()
        
        time.sleep(1)


if __name__ == "__main__":
    username = os.getenv("IGUSERNAME")
    password = os.getenv("IGPASSWORD")
    client = InstagramClient(username, password)
    client.login()

    # Initialize video queue
    video_queue = deque()

    # Fetch initial reels and load into mpv
    reels, last_pk = client.fetch_reels(last_pk=0, count=INITIAL_BUFFER)
    for url in reels:
        append_reel(url)
        video_queue.append(url)

    # Start buffer manager thread
    t = Thread(target=buffer_manager, args=(video_queue, client), daemon=True)
    t.start()

    # Keep main thread alive
    print("Reels CLI running. Use mpv controls or terminal keys to navigate.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting Reels CLI...")

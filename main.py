import subprocess
import time
from collections import deque
from threading import Thread
from instagram.instagram_client import InstagramClient
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
INITIAL_BUFFER = 8      # how many reels to load initially
MAX_FORWARD_BUFFER = 12  # keep at least this many reels ahead
MAX_BACKWARD_BUFFER = 3 # max reels to keep behind (dequeue older ones)
SOCKET = "/tmp/socket"

# Start mpv player with all initial videos
def start_mpv_with_playlist(video_urls):
    # Convert all URLs to strings and create command
    url_strings = [str(url) for url in video_urls]
    cmd = ["./run.sh"] + url_strings
    subprocess.Popen(cmd)
    time.sleep(4)  # wait longer for IPC socket to be ready


# Append a reel via q.sh
def append_reel(url: str):
    try:
        result = subprocess.run(["./q.sh", str(url)], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print(f"Failed to append reel: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("Timeout appending reel")
        return False
    except Exception as e:
        print(f"Error appending reel: {e}")
        return False


# Remove first reel via dq.sh
def remove_first_reel():
    try:
        result = subprocess.run(["./dq.sh"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception as e:
        print(f"Error removing reel: {e}")
        return False


# Get current playlist size from mpv
def get_playlist_size():
    try:
        result = subprocess.run(['nc', '-U', SOCKET, '-w', '1'], 
                              input='{ "command": ["get_property", "playlist-count"] }\n',
                              capture_output=True, text=True, timeout=3)
        if result.returncode == 0 and result.stdout:
            import json
            response = json.loads(result.stdout.strip())
            if 'data' in response:
                return response['data']
    except:
        pass
    return 0


# Get current playlist position
def get_playlist_position():
    try:
        result = subprocess.run(['nc', '-U', SOCKET, '-w', '1'], 
                              input='{ "command": ["get_property", "playlist-pos"] }\n',
                              capture_output=True, text=True, timeout=3)
        if result.returncode == 0 and result.stdout:
            import json
            response = json.loads(result.stdout.strip())
            if 'data' in response:
                return response['data']
    except:
        pass
    return 0


# Thread to maintain forward buffer
def buffer_manager(client: InstagramClient, last_pk_ref: list, seen_urls: set):
    consecutive_failures = 0
    last_successful_fetch = time.time()
    
    while True:
        try:
            # Check current playlist size and position
            playlist_size = get_playlist_size()
            current_pos = get_playlist_position()
            remaining_videos = playlist_size - current_pos
            
            print(f"Playlist: {playlist_size} total, position {current_pos}, {remaining_videos} remaining")
            
            # Keep forward buffer filled based on remaining videos
            if remaining_videos < MAX_FORWARD_BUFFER:
                print(f"Only {remaining_videos} videos remaining, fetching more...")
                
                # Check if we need to re-login (session expired)
                time_since_fetch = time.time() - last_successful_fetch
                if time_since_fetch > 1800:  # 30 minutes
                    print("Session might be expired, attempting re-login...")
                    try:
                        client.login()
                        print("Re-login successful!")
                    except Exception as e:
                        print(f"Re-login failed: {e}")
                        time.sleep(60)  # Wait a minute before retrying
                        continue
                
                try:
                    reels, new_last_pk = client.fetch_reels(last_pk=last_pk_ref[0], count=8)
                    
                    if not reels:
                        print("No more reels available")
                        consecutive_failures += 1
                        if consecutive_failures > 5:
                            print("Multiple fetch failures, trying to re-login...")
                            try:
                                client.login()
                                consecutive_failures = 0
                                print("Re-login successful!")
                            except Exception as e:
                                print(f"Re-login failed: {e}")
                                time.sleep(120)  # Wait 2 minutes
                                continue
                        else:
                            time.sleep(10)
                            continue
                    
                    consecutive_failures = 0
                    last_successful_fetch = time.time()
                    last_pk_ref[0] = new_last_pk
                    
                    added_count = 0
                    for url in reels:
                        url_str = str(url)
                        # Skip if we've already seen this URL
                        if url_str in seen_urls:
                            print(f"Skipping duplicate URL")
                            continue
                            
                        if append_reel(url_str):
                            seen_urls.add(url_str)
                            added_count += 1
                            print(f"Added reel to playlist. Total added: {added_count}")
                        time.sleep(0.2)  # small pause to avoid flooding IPC
                    
                    if added_count == 0:
                        print("No new reels were added (all duplicates?)")
                        # Reset last_pk to get different content
                        last_pk_ref[0] = 0
                        time.sleep(15)
                    else:
                        print(f"Successfully added {added_count} new reels")
                        
                except Exception as e:
                    print(f"Error fetching reels: {e}")
                    consecutive_failures += 1
                    if "login_required" in str(e).lower():
                        print("Login required error, attempting re-login...")
                        try:
                            client.login()
                            consecutive_failures = 0
                            print("Re-login successful!")
                        except Exception as login_e:
                            print(f"Re-login failed: {login_e}")
                            time.sleep(60)
                    else:
                        time.sleep(10)
            else:
                # Playlist has enough videos, wait longer
                time.sleep(8)
            
        except Exception as e:
            print(f"Error in buffer manager: {e}")
            consecutive_failures += 1
            time.sleep(10)


def test_socket_connection():
    """Test if we can connect to mpv's IPC socket"""
    try:
        result = subprocess.run(['nc', '-U', SOCKET, '-w', '1'], 
                              input='{ "command": ["get_property", "filename"] }\n',
                              capture_output=True, text=True, timeout=3)
        return result.returncode == 0
    except:
        return False


def cleanup_old_items():
    """Remove items from the beginning of playlist if it gets too long"""
    try:
        playlist_size = get_playlist_size()
        current_pos = get_playlist_position()
        
        # Only cleanup items that are behind the current position
        if current_pos > MAX_BACKWARD_BUFFER:
            items_to_remove = current_pos - MAX_BACKWARD_BUFFER
            print(f"Cleaning up {items_to_remove} old items from playlist")
            for _ in range(items_to_remove):
                if not remove_first_reel():
                    break
                time.sleep(0.1)
    except Exception as e:
        print(f"Error during cleanup: {e}")


if __name__ == "__main__":
    username = os.getenv("IGUSERNAME")
    password = os.getenv("IGPASSWORD")
    
    if not username or not password:
        print("Error: IGUSERNAME and IGPASSWORD must be set in .env file")
        exit(1)
    
    print("Initializing Instagram client...")
    client = InstagramClient(username, password)
    
    # Login once at the beginning
    print("Logging in to Instagram...")
    try:
        client.login()
        print("Login successful!")
    except Exception as e:
        print(f"Initial login failed: {e}")
        exit(1)

    # Initialize tracking variables
    last_pk_ref = [0]  # Use list so it can be modified in thread
    seen_urls = set()  # Track URLs we've already added to prevent duplicates

    # Fetch initial reels
    print("Fetching initial reels...")
    try:
        reels, last_pk_ref[0] = client.fetch_reels(last_pk=0, count=INITIAL_BUFFER)
        if not reels:
            print("No reels found!")
            exit(1)
        print(f"Fetched {len(reels)} initial reels")
    except Exception as e:
        print(f"Failed to fetch initial reels: {e}")
        exit(1)

    # Add all initial URLs to seen set
    for url in reels:
        seen_urls.add(str(url))

    # Start mpv with all initial reels
    print("Starting mpv player with initial playlist...")
    start_mpv_with_playlist(reels)
    
    # Wait for socket to be ready
    print("Waiting for mpv IPC socket...")
    for i in range(20):  # Wait longer for socket
        if test_socket_connection():
            print("Socket ready!")
            break
        time.sleep(1)
        print(f"Still waiting... ({i+1}/20)")
    else:
        print("Warning: Socket not responding, continuing anyway...")

    print(f"Initial playlist loaded with {len(seen_urls)} unique reels")

    # Start buffer manager thread
    print("Starting buffer manager...")
    buffer_thread = Thread(target=buffer_manager, args=(client, last_pk_ref, seen_urls), daemon=True)
    buffer_thread.start()
    
    # Keep main thread alive
    print("Reels CLI running. Use mpv controls or terminal keys to navigate.")
    print("Press Ctrl+C to exit")
    try:
        cleanup_interval = 0
        while True:
            time.sleep(15)
            cleanup_interval += 1
            
            # Periodic cleanup every 5 minutes
            if cleanup_interval >= 20:  # 20 * 15 seconds = 5 minutes
                cleanup_old_items()
                cleanup_interval = 0
                
    except KeyboardInterrupt:
        print("\nExiting Reels CLI...")
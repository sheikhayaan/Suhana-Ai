import time

from worker import process_queue_once


if __name__ == "__main__":
    while True:
        print("Processing queue...")
        process_queue_once()
        time.sleep(4)
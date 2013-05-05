import time
import os

from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver# as Observer
from watchdog import events
from watchdog.tricks import LoggerTrick

import argparse
import logging
import random

logger = logging.getLogger('watchntouch')


class PollingHandler(events.FileSystemEventHandler):
    def __init__(self, options):
        self.options = options
        self.skip_next = set()

    def touch_file(self, event):
        if event.src_path == self.options.watchdir:
            logger.debug("Ignoring change to root watchdir...")
            return

        if event in self.skip_next:
            logger.debug("Event on skiplist: %s" % event)
            self.skip_next.remove(event)
            return

        logger.debug("Re-touching file for event: %s" % event)
        os.utime(event.src_path, None)


    on_modified = touch_file
    on_created = touch_file

    def on_deleted(self, event):
        if not self.options.simulate_rm:
            return
        if event.is_directory:
            logger.debug("Simulating native rmdir: %s" % event)
            os.mkdir(event.src_path)
            os.rmdir(event.src_path)
        else:
            logger.debug("Simulating native rm: %s" % event)
            os.makedirs(os.path.dirname(event.src_path))
            open(event.src_path, "a").close()
            os.remove(event.src_path)

    def on_moved(self, event):
        if not self.options.simulate_mv:
            return
        logger.debug("Simulating move: %s" % event)
        os.rename(event.dest_path, event.src_path)
        os.rename(event.src_path, event.dest_path)


class NativeHandler(events.FileSystemEventHandler):
    def __init__(self, other, options):
        self.other = other
        self.options = options

    def on_modified(self, event):
        logger.debug("Adding native event to skiplist: %s" % event)
        self.other.skip_next.add(event)





def run():
    parser = argparse.ArgumentParser(
        description='Poll a directory for changes and re-touch changed paths '
            'so that inotify-incapable mounts (like CIFS) recieve inotify '
            'events anyway.')

    parser.add_argument('-i', '--polling-interval',
        default=1.0,
        help="Polling interval in seconds",
        type=float,
        dest='interval'
    )
    parser.add_argument('-l', '--log-level',
        default=11,
        help="Logger verbosity level",
        type=int,
        dest='loglevel'
    )

    parser.add_argument("-r", "--simulate-rm",
        default=False,
        action='store_true',
        dest='simulate_rm',
        help="Simulate rm operations by natively flashing a path in/out of "
        "existance. Only use if you find your tools get confused when a file "
        "disapeared from under them."
    )

    parser.add_argument("-m", "--simulate-mv",
        default=False,
        action='store_true',
        dest='simulate_mv',
        help="Simulate mv operations by natively moving a path back and forth."
        " Only use if you find your tools require specific handling of"
        " move events."
    )

    parser.add_argument('-w', '--watchdir',
        default=".",
        required=False,
        help="the directory to watch for changes",
        dest="watchdir"
    )

    args = parser.parse_args()

    args.watchdir = os.path.realpath(os.path.abspath(args.watchdir))

    logging.basicConfig(level=args.loglevel, format="%(message)s (%(levelname)s)\n")


    logger.info("Watching %r", args.watchdir)

    polling_handler = PollingHandler(args)
    native_handler = NativeHandler(polling_handler, args)

    polling_observer = PollingObserver()
    native_observer = Observer()

    native_observer.schedule(native_handler, path=args.watchdir, recursive=True)
    native_observer.start()


    polling_observer.schedule(polling_handler, path=args.watchdir, recursive=True)
    polling_observer.start()

    try:
        while True:
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Shutdown")
        native_observer.stop()
        polling_observer.stop()


    native_observer.join()
    polling_observer.join()



if __name__ == "__main__":
    run()
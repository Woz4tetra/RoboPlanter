import sys
import time
import asyncio
import datetime

from camera import Camera
from timelapse import Timelapse
from planter_arduino import PlanterArduino
from logger_manager import LoggerManager

logger = LoggerManager.get_logger()


class Session:
    def __init__(self, wait_time):
        resolution = (2208, 1712)

        self.lights_on_date_range = [7, 18]  # time of day in hours
        self.pump_on_time = 60.0  # seconds
        self.pump_on_hours = [5, 12, 17, 22]  # time of day in hours

        self.camera = Camera(resolution)
        self.timelapse = Timelapse(self, self.camera, "../timelapse-images", wait_time)
        self.planter_arduino = PlanterArduino(self)

        self.pump_check_delay = 60.0
        self.lights_check_delay = 3600.0
        self.update_delay = 1.0 / 20.0

        self.loop = asyncio.get_event_loop()

        self.tasks = []

    def start(self):
        self.planter_arduino.start()
        self.timelapse.start()

        timelapse_task = asyncio.ensure_future(self.timelapse.run_timelapse())
        arduino_task = asyncio.ensure_future(self.run_arduino())
        pump_task = asyncio.ensure_future(self.check_pump())
        lights_task = asyncio.ensure_future(self.check_lights())

        self.tasks = [
            timelapse_task,
            arduino_task,
            pump_task,
            lights_task,
        ]
        logger.info("Session start!")

    def run(self):
        try:
            self.start()
            self.loop.run_until_complete(asyncio.wait(self.tasks, return_when=asyncio.FIRST_EXCEPTION))
        except BaseException as e:
            raise
        finally:
            self.stop()

        # FIRST_COMPLETED
        # ALL_COMPLETED

        for task in self.tasks:
            if self.check_task_result(task):
                logger.error("Encountered an error while running!")

    def get_pump_segment(self, now):
        assert sorted(self.pump_on_hours) == self.pump_on_hours
        current_hour = now.hour
        if 0 <= current_hour < self.pump_on_hours[0] or self.pump_on_hours[-1] <= current_hour < 24:
            return len(self.pump_on_hours) - 1
        else:
            for index in range(0, len(self.pump_on_hours - 1)):
                start = self.pump_on_hours[index]
                stop = self.pump_on_hours[index + 1]
                if start <= hour < stop:
                    return index
        raise Exception("Invalid hour received: %s" % current_hour)

    async def check_pump(self):
        logger.info("check_pump task started")
        prev_segment = None
        while True:
            now = datetime.datetime.now()
            current_segment = self.get_pump_segment(now)

            if current_segment != prev_segment:
                self.planter_arduino.set_pump(True)
                await asyncio.sleep(self.pump_on_time)
                self.planter_arduino.set_pump(False)

                prev_segment = current_segment

            await asyncio.sleep(self.pump_check_delay)

    async def check_lights(self):
        logger.info("check_lights task started")
        start_hour = self.lights_on_date_range[0]
        stop_hour = self.lights_on_date_range[1]
        while True:
            now = datetime.datetime.now()
            self.planter_arduino.set_grow_light(start_hour <= now.hour < stop_hour)
            await asyncio.sleep(self.lights_check_delay)


    async def run_arduino(self):
        logger.info("run_arduino task started")
        while True:
            self.planter_arduino.update()
            await asyncio.sleep(self.update_delay)


    def check_task_result(self, task):
        result = task.cancel()
        logger.debug("Cancelling %s: %s" % (task, result))
        exception_raised = False

        if task.cancelled():
            logger.debug("Task '%s' was cancelled" % task)
        elif task.done() and task.exception() is not None:
            try:
                raise task.exception()
            except:
                exception_raised = True
                logger.error("Error occurred in task:", exc_info=True)
        return exception_raised


    def stop(self):
        self.camera.close()
        self.planter_arduino.stop()


def main():
    print("Starting scallion-experiment-1 timelapse")
    WAIT_TIME = 10.0

    if len(sys.argv) > 1:
        try:
            WAIT_TIME = float(sys.argv[1])
        except ValueError:
            pass

    session = Session(3600.0)
    session.run()


if __name__ == '__main__':
    main()

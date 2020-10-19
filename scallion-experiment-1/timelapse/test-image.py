import sys
import time
import asyncio
import datetime
from aioconsole import ainput

from camera import Camera
from timelapse import Timelapse
from planter_arduino import PlanterArduino
from logger_manager import LoggerManager

logger = LoggerManager.get_logger()


class Session:
    def __init__(self):
        resolution = (2208, 1712)

        self.camera = Camera(resolution)
        self.timelapse = Timelapse(self, self.camera, "../timelapse-images", 10.0)
        self.planter_arduino = PlanterArduino(self)

        self.update_delay = 1.0 / 20.0

        self.loop = asyncio.get_event_loop()

        self.tasks = []

    def start(self):
        self.planter_arduino.start()
        self.timelapse.start()

        arduino_task = asyncio.ensure_future(self.run_arduino())
        keyboard_task = asyncio.ensure_future(self.run_keyboard())

        self.tasks = [
            arduino_task,
            keyboard_task,
        ]
        logger.info("Session start!")

    async def run_keyboard(self):
        while True:
            line = await ainput("> ")
            line = line.strip()
            logger.info("Keyboard: %s" % line)
            try:
                if line[0] == "l":
                    self.planter_arduino.set_grow_light(int(line[1]))
                elif line[0] == "p":
                    self.planter_arduino.set_pump(int(line[1]))
                elif line[0] == "t":
                    await self.timelapse.take_photo()
            except BaseException as e:
                logger.error(str(e), exc_info=True)


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
    print("Starting scallion-experiment-1 test image")

    session = Session()
    session.run()


if __name__ == '__main__':
    main()

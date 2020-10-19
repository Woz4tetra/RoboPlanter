import os
import cv2
import time
import datetime
import asyncio

from logger_manager import LoggerManager

logger = LoggerManager.get_logger()


class Timelapse:
    def __init__(self, session, camera, out_dir, wait_time):
        self.base_out_dir = out_dir
        self.out_subdir_timestamp_format = "%Y-%m-%d"
        self.out_name_timestamp_format = "%Y-%m-%dT%H-%M-%S--%f"
        self.out_name = "img{0}-{1}.jpg"

        self.count = 0
        self.should_stop = False
        self.dir_index = 0

        self.wait_time = wait_time
        self.camera = camera

        self.compute_outdir_index()
        now = datetime.datetime.now()
        self.out_dir = self.get_outdir(now)

        self.session = session
        self.planter_arduino = None

    def start(self):
        self.planter_arduino = self.session.planter_arduino

    def set_wait_time(self, wait_time):
        self.wait_time = wait_time

    async def run_timelapse(self):
        logger.info("Timelapse has started")
        try:
            while not self.should_stop:
                await self.take_photo()
                await self.delay()
        except BaseException as e:
            raise
        finally:
            logger.info("Stopping timelapse")

    async def take_photo(self):
        lights_were_on = self.planter_arduino.get_grow_light()
        if not lights_were_on:
            self.planter_arduino.set_grow_light(True)
            await asyncio.sleep(0.5)

        image = self.camera.take_photo()
        now = datetime.datetime.now()

        if not lights_were_on:
            await asyncio.sleep(0.5)
            self.planter_arduino.set_grow_light(False)

        out_name_timestamp = now.strftime(self.out_name_timestamp_format)

        filename = self.out_name.format(self.count, out_name_timestamp)
        out_path = os.path.join(self.out_dir, filename)

        print("Capturing image: %s" % out_path)
        cv2.imwrite(out_path, image)

        self.count += 1

    def get_outdir(self, now, makedirs=True):
        out_subdir_timestamp = now.strftime(self.out_subdir_timestamp_format)
        out_subdir_timestamp += "--" + str(self.dir_index)
        out_dir = os.path.join(self.base_out_dir, out_subdir_timestamp)
        if not os.path.isdir(out_dir) and makedirs:
            os.makedirs(out_dir)
        return out_dir

    def compute_outdir_index(self):
        now = datetime.datetime.now()
        outdir = ""
        while self.dir_index < 1000:
            outdir = self.get_outdir(now, False)
            if os.path.isdir(outdir):
                self.dir_index += 1
            else:
                break
        if os.path.isdir(outdir):
            raise Exception("Failed to create directory. Index count exceeded.")

    async def delay(self):
        await asyncio.sleep(self.wait_time)

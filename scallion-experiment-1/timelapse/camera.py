import picamera
from picamera.array import PiRGBArray


class Camera:
    def __init__(self, resolution):
        self.camera = picamera.PiCamera()
        self.camera.resolution = resolution
        # self.camera.hflip = True
        # self.camera.vflip = True
        self.camera.rotation = 90
        self.raw_capture = PiRGBArray(self.camera, size=self.camera.resolution)

    def take_photo(self):
        self.camera.capture(self.raw_capture, format="bgr")
        image = self.raw_capture.array
        self.raw_capture.truncate(0)
        return image

    def close(self):
        self.camera.close()

import time
import serial
import datetime
import threading

from task import Task
from device_port import DevicePort
from logger_manager import LoggerManager
from exceptions import DeviceNotReadyException

logger = LoggerManager.get_logger()


class PlanterArduino:
    def __init__(self, session):
        self.session = session

        self.device = DevicePort(
            "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_75735353238351C0F150-if00",
            115200,
            5.0,
            5.0
        )

        self.should_stop = False
        self.serial_device_paused = False

        self.read_task = Task(self.read_task_fn)

        self.read_update_rate_hz = 60.0
        self.update_delay = 1.0 / self.read_update_rate_hz

        self.prev_packet_time = 0.0

        self.write_packet_num = 0
        self.read_packet_num = -1
        self.recv_packet_num = 0

        self.prev_packet_num_report_time = 0.0

        self.write_lock = threading.Lock()
        self.read_lock = threading.Lock()

        self.PACKET_START_0 = b'h'
        self.PACKET_START_1 = b'i'
        self.PACKET_STOP = b'\n'
        self.PACKET_SEP = b'\t'
        self.PACKET_SEP_STR = '\t'

        self.ready_state = {
            "name"    : "",
            "is_ready": False,
            "time_ms" : 0
        }

        self.planter_state = {
            "recv_time"    : 0.0,
            "is_active"    : False,
        }

        self.pump_state = False
        self.lights_state = False

        self.read_buffer = ""
        self.buffer_index = 0
        self.current_segment = ""
        self.current_segment_num = 0
        self.parsed_data = []
        self.recv_time = 0.0

        self.check_ready_timeout = 5.0
        self.write_timeout = 1.0
        self.packet_start_timeout = 0.15

        self.packet_error_codes = {
            0: "no error",
            1: "c1 != \\x12",
            2: "c2 != \\x34",
            3: "packet is too short",
            4: "checksums don't match",
            5: "packet count segment not found",
            6: "packet counts not synchronized",
            7: "failed to find category segment",
            8: "invalid format",
        }

        self.device_start_time = 0.0
        self.offset_time_ms = 0

        self.is_active = False

    def start(self):
        logger.info("Starting planter arduino client")

        self.device.configure()
        logger.info("Device configured")

        self.read_task.start()
        logger.info("Read thread started")
        time.sleep(1.0)

        self.check_ready()
        self.prev_command_time = time.time()

        self.set_reporting(True)
        self.set_active(True)

    def process_packet(self, category):
        if category == "txrx" and self.parse_segments("dd"):
            packet_num = self.parsed_data[0]
            error_code = self.parsed_data[1]

            if error_code != 0:
                self.log_packet_error_code(error_code, packet_num)
            else:
                logger.debug("No error in transmitted packet #%s" % packet_num)

        elif category == "ready" and self.parse_segments("ds"):
            self.ready_state["time_ms"] = self.parsed_data[0]
            self.ready_state["name"] = self.parsed_data[1]
            self.ready_state["is_ready"] = True

            logger.info("Ready signal received! %s" % self.ready_state)

        elif category == "state" and self.parse_segments("uddd"):
            self.planter_state["recv_time"] = self.get_device_time(self.parsed_data[0])
            self.planter_state["is_active"] = self.parsed_data[1]
            self.planter_state["battery_ok"] = self.parsed_data[2]
            self.planter_state["motors_active"] = self.parsed_data[3]

    def get_grow_light(self):
        return self.lights_state

    def set_grow_light(self, state):
        state = bool(state)
        logger.debug("Received grow light state: %s" % state)
        if state != self.lights_state:
            self.lights_state = state
            logger.info("Setting lights to %s" % self.lights_state)
            self.write("light", int(self.lights_state))

    def set_pump(self, state):
        state = bool(state)
        logger.debug("Received pump state: %s" % state)
        if state != self.pump_state:
            self.pump_state = state
            logger.info("Setting pump to %s" % self.pump_state)
            self.write("pump", int(self.pump_state))

    def set_reporting(self, state):
        self.write("[]", 1 if state else 0)

    def set_active(self, state):
        self.is_active = state
        self.write("<>", 1 if state else 0)

    def check_ready(self):
        self.write("?", "planter-arduino")

        begin_time = time.time()
        write_time = time.time()

        while not self.ready_state["is_ready"]:
            if time.time() - begin_time > self.check_ready_timeout:
                break
            if time.time() - write_time > self.write_timeout:
                logger.info("Writing ready signal again")
                self.write("?", "planter-arduino")
                write_time = time.time()

            if self.device.in_waiting() > 2:
                self.read()

        if self.ready_state["is_ready"]:
            self.set_start_time(self.ready_state["time_ms"])
            logger.info("Serial device is ready. Robot name is %s" % self.ready_state["name"])
        else:
            raise DeviceNotReadyException("Failed to receive ready signal within %ss" % self.check_ready_timeout)

    def update(self):
        if not self.read_task.is_errored():
            logger.error("Error detected in read task. Raising exception")
            raise self.read_task.thread_exception

        current_time = time.time()
        if current_time - self.prev_packet_num_report_time > 60.0:
            logger.info("Packet numbers. Read: %s; Write: %s" % (self.read_packet_num, self.write_packet_num))
            self.prev_packet_num_report_time = current_time

    def stop(self):
        if self.should_stop:
            logger.info("Stop flag already set")
            return

        logger.info("Stopping planter arduino client")

        self.should_stop = True
        logger.info("Set stop flag")

        self.read_task.stop()

        self.pre_serial_stop_callback()

        self.set_reporting(False)
        self.set_active(False)

        time.sleep(0.1)

        with self.read_lock:
            self.device.stop()
        logger.info("Device connection closed")

    def pre_serial_stop_callback(self):
        pass

    def write(self, name, *args):
        if self.serial_device_paused:
            logger.debug("Serial device is paused. Skipping write: %s, %s" % (str(name), str(args)))
            return

        packet = b""
        packet += self.PACKET_START_0
        packet += self.PACKET_START_1
        packet += str(self.write_packet_num).encode()
        packet += self.PACKET_SEP + str(name).encode()
        for arg in args:
            packet += self.PACKET_SEP + str(arg).encode()

        calc_checksum = 0
        for val in packet[2:]:
            calc_checksum += val
        calc_checksum &= 0xff

        packet += b"%02x" % calc_checksum
        packet += self.PACKET_STOP

        with self.write_lock:
            logger.debug("Writing %s" % str(packet))
            try:
                self.device.write(packet)
            except BaseException as e:
                logger.error("Exception while writing packet %s: %s" % (packet, str(e)), exc_info=True)

            self.write_packet_num += 1
            time.sleep(0.0005)  # give the microcontroller a chance to not drop the next packet

    def wait_for_packet_start(self):
        begin_time = time.time()
        msg_buffer = b""
        c1 = ""
        c2 = ""

        while True:
            if time.time() - begin_time > self.packet_start_timeout:
                return False

            if self.device.in_waiting() < 2:
                continue

            c1 = self.device.read(1)
            # logger.info("buffer: %s" % msg_buffer)
            if c1 == self.PACKET_START_0:
                c2 = self.device.read(1)
                if c2 == self.PACKET_START_1:
                    return True
            elif c1 == self.PACKET_STOP:
                time.sleep(self.update_delay)
                logger.info("Device message: %s" % (msg_buffer.decode()))
                msg_buffer = b""
            else:
                msg_buffer += c1

    def get_next_segment(self):
        if self.buffer_index >= len(self.read_buffer):
            return False

        sep_index = self.read_buffer.find(self.PACKET_SEP_STR, self.buffer_index)
        if sep_index == -1:
            self.current_segment = self.read_buffer[self.buffer_index:]
            self.buffer_index = len(self.read_buffer)
        else:
            self.current_segment = self.read_buffer[self.buffer_index: sep_index]
            self.buffer_index = sep_index + 1
        return True

    def read(self):
        with self.read_lock:
            return self._read()

    def readline(self):
        buffer = b""
        while True:
            if self.device.in_waiting():
                c = self.device.read(1)
                if c == self.PACKET_STOP:
                    break
                buffer += c
        return buffer

    def _read(self):
        # if self.serial_device_paused:
        #     logger.debug("Serial device is paused. Skipping read")
        #     return

        if not self.wait_for_packet_start():
            return False

        buffer = self.readline()
        logger.debug("buffer: %s" % buffer.decode())

        if len(buffer) < 5:
            logger.error("Received packet has an invalid number of characters! %s" % repr(buffer.decode()))
            self.read_packet_num += 1
            return False

        calc_checksum = 0
        for val in buffer[:-2]:
            calc_checksum += val
        calc_checksum &= 255

        self.read_buffer = buffer.decode()
        try:
            recv_checksum = int(self.read_buffer[-2:], 16)
        except ValueError as e:
            logger.error("Failed to parsed checksum as hex int: %s" % repr(self.read_buffer))
            self.read_packet_num += 1
            return False
        self.read_buffer = self.read_buffer[:-2]
        if calc_checksum != recv_checksum:
            logger.error(
                "Checksum failed! recv %s != calc %s. %s" % (recv_checksum, calc_checksum, repr(self.read_buffer)))
            self.read_packet_num += 1
            return False

        self.buffer_index = 0

        # get packet num segment
        if not self.get_next_segment():
            logger.error(
                "Failed to find packet number segment %s! %s" % (repr(self.current_segment), repr(self.read_buffer)))
            self.read_packet_num += 1
            return False
        self.recv_packet_num = int(self.current_segment)
        if self.read_packet_num == -1:
            self.read_packet_num = self.recv_packet_num
        if self.recv_packet_num != self.read_packet_num:
            logger.warning("Received packet num doesn't match local count. "
                           "recv %s != local %s", self.recv_packet_num, self.read_packet_num)
            logger.debug("Buffer: %s" % self.read_buffer)
            self.read_packet_num = self.recv_packet_num

        # find category segment
        if not self.get_next_segment():
            logger.error(
                "Failed to find category segment %s! %s" % (repr(self.current_segment), repr(self.read_buffer)))
            self.read_packet_num += 1
            return False
        category = self.current_segment

        try:
            self.process_packet(category)
        except BaseException as e:
            logger.error("Exception while processing packet %s: %s" % (self.read_buffer, str(e)), exc_info=True)
            return False

        self.read_packet_num += 1
        return True

    def parse_segments(self, formats):
        self.parsed_data = []
        self.recv_time = time.time()
        for index, f in enumerate(formats):
            if not self.get_next_segment():
                logger.error("Failed to parse segment #%s. Buffer: %s" % (index, self.read_buffer))
                return False
            if f == 'd' or f == 'u':
                self.parsed_data.append(int(self.current_segment))
            elif f == 's':
                self.parsed_data.append(self.current_segment)
            elif f == 'f':
                self.parsed_data.append(float(self.current_segment))
        return True

    def read_task_fn(self, should_stop):
        self.prev_packet_time = time.time()

        while True:
            time.sleep(self.update_delay)
            if should_stop():
                logger.info("Exiting read thread")
                return

            while self.device.in_waiting() > 2:
                self.read()

    def log_packet_error_code(self, error_code, packet_num):
        logger.warning("Packet %s returned an error:" % packet_num)
        logger.warning("\t%s" % self.packet_error_codes.get(error_code, "unknown error code: '%s'" % error_code))

    def set_start_time(self, time_ms):
        self.device_start_time = time.time()
        self.offset_time_ms = time_ms

    def get_device_time(self, time_ms):
        return self.device_start_time + (time_ms - self.offset_time_ms) / 1000.0

    def pause_serial_device(self):
        logger.info("Pausing serial device")
        self.serial_device_paused = True

    def resume_serial_device(self):
        logger.info("Resuming serial device")
        self.serial_device_paused = False

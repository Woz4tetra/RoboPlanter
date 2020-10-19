#include <Arduino.h>
#include "planter-serial.h"

struct state {
    bool is_reporting_enabled;
    bool is_active;
} planter_state;

#define CURRENT_TIME millis()

const int RELAY1 = 2;
const int RELAY2 = 3;
const int RELAY3 = 4;
const int RELAY4 = 5;

bool relay1_state = LOW;
bool relay2_state = LOW;
bool relay3_state = LOW;
bool relay4_state = LOW;

#define PUMP_RELAY RELAY1
#define LIGHTS_RELAY RELAY2

void init_structs() {
    planter_state.is_reporting_enabled = false;
    planter_state.is_active = false;
}


void set_relay(int index, bool state) {
    switch (index) {
        case RELAY1:
            relay1_state = state;
            digitalWrite(RELAY1, relay1_state);
            break;
        case RELAY2:
            relay2_state = state;
            digitalWrite(RELAY2, relay2_state);
            break;
        case RELAY3:
            relay3_state = state;
            digitalWrite(RELAY3, relay3_state);
            break;
        case RELAY4:
            relay4_state = state;
            digitalWrite(RELAY4, relay4_state);
            break;
        default:
            break;
    }
}

bool get_relay(int index) {
    switch (index) {
        case RELAY1: return relay1_state;
        case RELAY2: return relay2_state;
        case RELAY3: return relay3_state;
        case RELAY4: return relay4_state;
        default: return false;
    }
}

void set_all_relays(bool state) {
    for (size_t i = 1; i <= 4; i++) {
        set_relay(i, state);
    }
}

void set_active(bool state) {
    if (state == planter_state.is_active) {
        return;
    }
    planter_state.is_active = state;
    if (!state) {
        set_all_relays(false);
    }
}

void planter_serial::packet_callback(planter_serial::PlanterSerial* serial_obj, String category, String packet)
{
    // get_ready
    if (category.equals("?")) {
        CHECK_SEGMENT(serial_obj);
        if (serial_obj->get_segment().equals("planter-arduino")) {
            planter_serial::println_info("Received ready signal!");
            planter_serial::data->write("ready", "us", (unsigned int)CURRENT_TIME, "planter");
        }
        else {
            planter_serial::println_error("Invalid ready segment supplied: %s", serial_obj->get_segment().c_str());
        }
    }

    // toggle reporting
    else if (category.equals("[]")) {
        CHECK_SEGMENT(serial_obj);
        int reporting_state = serial_obj->get_segment().toInt();
        switch (reporting_state)
        {
            case 0: planter_state.is_reporting_enabled = false; break;
            case 1: planter_state.is_reporting_enabled = true; break;
            // case 2: reset(); break;
            default:
                planter_serial::println_error("Invalid reporting flag received: %d", reporting_state);
                break;
        }
    }

    // toggle motors active
    else if (category.equals("<>")) {
        CHECK_SEGMENT(serial_obj);
        int active_state = serial_obj->get_segment().toInt();
        switch (active_state)
        {
            case 0: set_active(false); break;
            case 1: set_active(true); break;
            default:
                break;
        }
    }

    // Lights
    else if (category.equals("light")) {
        CHECK_SEGMENT(serial_obj); bool state = (bool)serial_obj->get_segment().toInt();
        set_relay(LIGHTS_RELAY, state);
    }

    // Pump
    else if (category.equals("pump")) {
        CHECK_SEGMENT(serial_obj); bool state = (bool)serial_obj->get_segment().toInt();
        set_relay(PUMP_RELAY, state);
    }
}


void setup()
{
    pinMode(RELAY1, OUTPUT);
    pinMode(RELAY2, OUTPUT);
    pinMode(RELAY3, OUTPUT);
    pinMode(RELAY4, OUTPUT);

    init_structs();

    planter_serial::setup_serial();
    set_all_relays(false);
}

void loop()
{
    planter_serial::data->read();
}

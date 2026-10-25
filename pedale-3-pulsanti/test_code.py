"""Simulate Pico button timings with USB HID replaced by a fake keyboard."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import sys
import unittest


class EndSimulation(Exception):
    pass


def simulate(schedule, until):
    now = 0.0
    events = list(schedule)
    output = []

    class Keyboard:
        def __init__(self, _devices):
            pass

        def release_all(self):
            pass

        def press(self, key):
            output.append((round(now, 3), "press", key))

        def release(self, key):
            output.append((round(now, 3), "release", key))

    class EventQueue:
        def get(self):
            if events and events[0][0] <= now + 0.0001:
                _, index, pressed = events.pop(0)
                return SimpleNamespace(key_number=index, pressed=pressed)
            return None

    class Keys:
        def __init__(self, *_args, **_kwargs):
            self.events = EventQueue()

    def sleep(seconds):
        nonlocal now
        now += seconds
        if now > until:
            raise EndSimulation

    fake_time = ModuleType("time")
    fake_time.monotonic = lambda: now
    fake_time.sleep = sleep
    modules = {
        "board": SimpleNamespace(GP2=2, GP3=3, GP4=4),
        "keypad": SimpleNamespace(Keys=Keys),
        "time": fake_time,
        "usb_hid": SimpleNamespace(devices=()),
        "adafruit_hid": ModuleType("adafruit_hid"),
        "adafruit_hid.keyboard": SimpleNamespace(Keyboard=Keyboard),
        "adafruit_hid.keycode": SimpleNamespace(Keycode=SimpleNamespace(
            LEFT_ARROW="left", ENTER="enter", RIGHT_ARROW="right", F12="f12")),
    }
    source = Path(__file__).with_name("code.py")
    with patch.dict(sys.modules, modules):
        try:
            exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), {})
        except EndSimulation:
            pass
    return output


class PedalTests(unittest.TestCase):
    def test_short_prev_click(self):
        output = simulate([(0, 0, True), (0.08, 0, False)], 0.2)
        self.assertEqual([(action, key) for _, action, key in output],
                         [("press", "left"), ("release", "left")])

    def test_single_held_prev_has_real_press_and_release(self):
        output = simulate([(0, 0, True), (1.0, 0, False)], 1.1)
        self.assertEqual([(action, key) for _, action, key in output],
                         [("press", "left"), ("release", "left")])
        self.assertGreaterEqual(output[0][0], 0.18)
        self.assertAlmostEqual(output[1][0], 1.0, places=2)

    def test_chord_emits_only_f12_after_three_seconds(self):
        output = simulate([(0, 0, True), (0.05, 2, True),
                           (3.2, 0, False), (3.25, 2, False)], 3.4)
        self.assertEqual([(action, key) for _, action, key in output],
                         [("press", "f12"), ("release", "f12")])
        self.assertGreaterEqual(output[0][0], 3.05)

    def test_aborted_chord_does_nothing(self):
        output = simulate([(0, 0, True), (0.05, 2, True),
                           (0.5, 0, False), (0.55, 2, False)], 3.4)
        self.assertEqual(output, [])


if __name__ == "__main__":
    unittest.main()

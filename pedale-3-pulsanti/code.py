"""Pedale USB a tre pulsanti per Raspberry Pi Pico W.

Cablaggio: ogni pulsante collega il proprio GPIO a GND quando viene premuto.
GP2 = PREV, GP3 = SELECT/MENU, GP4 = NEXT.
"""

import board
import keypad
import time
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# Cambia ENTER in SPACE se il tuo programma usa la barra spaziatrice per Select.
KEYS = (
    Keycode.LEFT_ARROW,  # PREV (puoi sostituire con Keycode.UP_ARROW)
    Keycode.ENTER,       # SELECT / MENU
    Keycode.RIGHT_ARROW, # NEXT (puoi sostituire con Keycode.DOWN_ARROW)
)

keyboard = Keyboard(usb_hid.devices)
keyboard.release_all()

# Aspetta un istante prima di inviare Prev/Next: due pressioni quasi
# contemporanee non devono spostare la scaletta prima del menu alimentazione.
CHORD_WINDOW = 0.18
CHORD_SECONDS = 3.0

# pull=True attiva le resistenze interne: nessuna resistenza esterna necessaria.
buttons = keypad.Keys(
    (board.GP2, board.GP3, board.GP4),
    value_when_pressed=False,
    pull=True,
)

held = [False, False, False]
sent = [False, False, False]
pending = {}
chord_active = False
chord_started = 0.0
chord_sent = False

while True:
    event = buttons.events.get()
    while event is not None:
        index = event.key_number
        held[index] = event.pressed
        if index == 1:
            if event.pressed:
                keyboard.press(KEYS[index])
            else:
                keyboard.release(KEYS[index])
        elif chord_active:
            # Dopo una combinazione, attendi il rilascio di entrambi i pedali.
            if not held[0] and not held[2]:
                chord_active = False
                chord_sent = False
        elif held[0] and held[2]:
            for nav_index in (0, 2):
                pending.pop(nav_index, None)
                if sent[nav_index]:
                    keyboard.release(KEYS[nav_index])
                    sent[nav_index] = False
            chord_active = True
            chord_started = time.monotonic()
        elif event.pressed:
            pending[index] = time.monotonic()
        else:
            pending.pop(index, None)
            if sent[index]:
                keyboard.release(KEYS[index])
                sent[index] = False
            else:
                keyboard.press(KEYS[index])
                keyboard.release(KEYS[index])
        event = buttons.events.get()

    now = time.monotonic()
    if chord_active and held[0] and held[2] and not chord_sent and now - chord_started >= CHORD_SECONDS:
        keyboard.press(Keycode.F12)
        keyboard.release(Keycode.F12)
        chord_sent = True
    if not chord_active:
        for index in (0, 2):
            if index in pending and held[index] and now - pending[index] >= CHORD_WINDOW:
                keyboard.press(KEYS[index])
                sent[index] = True
                pending.pop(index)
    time.sleep(0.005)

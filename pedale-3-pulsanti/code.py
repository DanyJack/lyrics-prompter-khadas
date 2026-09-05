"""Pedale USB a tre pulsanti per Raspberry Pi Pico W.

Cablaggio: ogni pulsante collega il proprio GPIO a GND quando viene premuto.
GP2 = PREV, GP3 = SELECT/MENU, GP4 = NEXT.
"""

import board
import keypad
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

# pull=True attiva le resistenze interne: nessuna resistenza esterna necessaria.
buttons = keypad.Keys(
    (board.GP2, board.GP3, board.GP4),
    value_when_pressed=False,
    pull=True,
)

while True:
    event = buttons.events.get()
    if event and event.pressed:
        keyboard.send(KEYS[event.key_number])

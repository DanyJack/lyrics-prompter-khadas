#!/bin/sh
set -eu
export DISPLAY=${DISPLAY:-:0}
export XAUTHORITY=${XAUTHORITY:-/home/khadas/.Xauthority}
exec 9>"${XDG_RUNTIME_DIR:-/run/user/1000}/lyrics-prompter.lock"
flock -n 9 || exit 0
xrandr --output HDMI-1 --mode 1680x1050p60hz --rotate left
xset s off -dpms
xsetroot -solid black -cursor_name blank || xsetroot -solid black
cd /home/khadas/lyrics-prompter/khadas-player
exec /usr/bin/python3 player.py

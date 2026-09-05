#!/bin/sh
set -eu
xsetroot -solid black
xset s off -dpms
xfwm4 --compositor=off &
wm_pid=$!
trap 'kill "$wm_pid" 2>/dev/null || true' EXIT
attempt=0
until xprop -root _NET_SUPPORTING_WM_CHECK 2>/dev/null | grep -q 'window id'; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 50 ] || exit 1
    sleep 0.1
done
while :; do
    /home/khadas/lyrics-prompter/boot-setup/start-prompter.sh >>"${XDG_RUNTIME_DIR:-/run/user/1000}/prompter-session.log" 2>&1 || true
    sleep 2
done
